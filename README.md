# RAGfier — Hybrid RAG API

Multi-tenant Retrieval-Augmented Generation backbone. Phase 1 ingests
PDFs/Markdown into Supabase `pgvector` with full citation metadata and
Row-Level Security. Phase 2 turns that index into a production-quality
query pipeline: hybrid retrieval (dense + sparse + RRF), cross-encoder
reranking, and citation-enforced LLM generation with hallucination
guardrails and SSE streaming.

See [SPEC.md](SPEC.md) (Phase 2) and [SPEC_Phase1.md](SPEC_Phase1.md) for the
full technical specs, and [AGENTS.md](AGENTS.md) for coding conventions.

## Configuration Model

RAGfier uses a hybrid configuration model:

- **Sensitive values** (API keys, tokens, service-role credentials) live in environment variables / `.env`.
- **Non-sensitive runtime defaults** live in [config/config.defaults.json](config/config.defaults.json) and are committed to source control.

Settings precedence (highest to lowest):

1. Explicit initialization values
2. Environment variables
3. `.env`
4. JSON defaults file (`config/config.defaults.json`)

This keeps deploy-time secrets out of source control while making safe defaults auditable and versioned.

## Architecture

### Ingestion (Phase 1)

```
Upload → Supabase Storage → LlamaParse → Chunker → OpenAI Embeddings → pgvector
```

- **Parser** — [app/pipeline/parser.py](app/pipeline/parser.py): LlamaParse for PDFs, in-process Markdown parser. Tracks section headings and spatial metadata.
- **Chunker** — [app/pipeline/chunker.py](app/pipeline/chunker.py): `RecursiveCharacterTextSplitter`, 700-token target / 100 overlap, tiktoken `cl100k_base`. Prepends document title + section heading to every chunk.
- **Embedder** — [app/pipeline/embedder.py](app/pipeline/embedder.py): OpenAI `text-embedding-3-small` (1536d), batch size 100, exponential backoff (max 3 retries).
- **Upserter** — [app/pipeline/upserter.py](app/pipeline/upserter.py): Batch insert into `documents` with full metadata JSONB; updates `ingestion_jobs.status` at every step.
- **Orchestrator** — [app/pipeline/orchestrator.py](app/pipeline/orchestrator.py): Coordinates the full parse → chunk → embed → upsert flow under a single `job_id`.

### Query pipeline (Phase 2)

```
Query → Embed → Hybrid Retrieve (dense ∥ sparse ⇒ RRF) → Rerank → Guardrail → Prompt → LLM → Citations
```

- **Dense retrieval** — [app/pipeline/retriever_dense.py](app/pipeline/retriever_dense.py): cosine similarity via `match_documents` (HNSW + `vector_cosine_ops`).
- **Sparse retrieval** — [app/pipeline/retriever_sparse.py](app/pipeline/retriever_sparse.py): BM25-equivalent via Postgres `tsvector` + `websearch_to_tsquery` on a generated `fts` column. The `HybridRetriever` runs both branches + RRF inside the `match_documents_hybrid` SQL function.
- **Reciprocal Rank Fusion** — [app/pipeline/fusion.py](app/pipeline/fusion.py): pure-Python RRF (`1 / (k + rank)`, `k=60`) used by the in-process fallback path and tests.
- **Reranker** — [app/pipeline/reranker.py](app/pipeline/reranker.py): Cohere `rerank-english-v3.0` primary + local `cross-encoder/ms-marco-MiniLM-L-6-v2` fallback behind a single `Reranker` facade. Auto-falls-back on API failure and reports the provider actually used.
- **Hallucination guardrail** — [app/pipeline/reranker.py:check_relevance](app/pipeline/reranker.py): declines with the canonical "not enough information" message when the top rerank score is below `RELEVANCE_THRESHOLD`, or when retrieval is empty.
- **Generator** — [app/pipeline/generator.py](app/pipeline/generator.py): OpenAI `gpt-4o` (configurable) with retry-wrapped `generate()` and async `stream()`; model/temperature/max_tokens are pulled from the prompt config.
- **Citation resolver** — [app/pipeline/citation_resolver.py](app/pipeline/citation_resolver.py): `assemble_context()` injects `[SOURCE_N]` headers with document / section / page; `resolve_citations()` parses the generated text and returns `Citation` objects with full metadata and rerank/RRF scores.
- **Prompt loader** — [app/utils/prompt_loader.py](app/utils/prompt_loader.py): tenant-DB override > global-DB prompt > YAML file ([prompts/rag_generation_v1.yaml](prompts/rag_generation_v1.yaml)).
- **Query orchestrator** — [app/pipeline/query_pipeline.py](app/pipeline/query_pipeline.py): shared `prepare_query()` that runs embed → hybrid retrieve → rerank → guardrail → context assembly, returning a `PreparedQuery` reused by both the sync and streaming endpoints. Tracks per-step latency in `RetrievalMetadata.latency_ms`.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ingest` | Upload a PDF or Markdown file; returns `job_id` |
| `GET`  | `/status/{job_id}` | Poll pipeline progress |
| `POST` | `/query` | Hybrid retrieval → rerank → generation with resolved `[SOURCE_N]` citations |
| `POST` | `/query/stream` | Same pipeline, streamed as SSE: `sources` → `token`… → `done` |
| `GET`  | `/prompts` | List tenant + global prompt versions |
| `POST` | `/prompts` | Create a new prompt version (auto-deactivates the previous active one) |
| `GET`  | `/health` | Service health (Supabase, OpenAI, Cohere) |

All tenant-scoped endpoints require `Authorization: Bearer <jwt>` where the
JWT contains `app_metadata.organization_id`. An `X-Tenant-Id` header override
is accepted for local testing.

### `/query` response shape

```json
{
  "query": "What is the liability cap?",
  "answer": "The liability cap shall not exceed $1,000,000 [SOURCE_1]...",
  "citations": [
    {
      "source_id": "SOURCE_1",
      "chunk_id": "…",
      "content": "The liability cap shall not exceed…",
      "metadata": { "source": "contract.pdf", "page_number": 5, "bounding_boxes": [[72,340,540,380]], "section_heading": "Section 3.2 — Limitation of Liability", "document_title": "Master Services Agreement" },
      "rerank_score": 0.95,
      "rrf_score": 0.032
    }
  ],
  "retrieval_metadata": {
    "dense_results": 20,
    "sparse_results": 12,
    "rrf_candidates": 26,
    "reranked_top_k": 5,
    "model": "gpt-4o",
    "prompt_version": "rag_generation_v1:v1",
    "reranker_provider": "cohere",
    "latency_ms": { "embedding": 45, "retrieval": 50, "reranking": 380, "generation": 1200, "total": 1677 }
  },
  "declined": false
}
```

### `/query/stream` SSE events

```
event: sources
data: {"citations": [...]}          ← sent before generation begins

event: token
data: The

event: token
data:  liability
…
event: done
data: {"retrieval_metadata": {...}, "declined": false}
```

The `sources` event lets a frontend render citation cards while tokens
stream in. Declines emit a single synthetic `token` event followed by
`done` with `declined: true`.

## Project Layout

```
RAGfier/
├── app/
│   ├── main.py                  FastAPI app + lifespan
│   ├── config.py                Pydantic Settings (Phase 1 + Phase 2)
│   ├── api/
│   │   ├── ingest.py            POST /ingest
│   │   ├── status.py            GET /status/{job_id}
│   │   ├── query.py             POST /query  (hybrid + rerank + generation)
│   │   ├── query_stream.py      POST /query/stream  (SSE)
│   │   ├── prompts.py           GET/POST /prompts
│   │   ├── health.py            GET /health
│   │   └── auth.py              JWT tenant resolution
│   ├── pipeline/
│   │   ├── parser.py            LlamaParse + MD
│   │   ├── chunker.py           recursive character splitter
│   │   ├── embedder.py          OpenAI batch embeddings
│   │   ├── upserter.py          Supabase batch upsert
│   │   ├── orchestrator.py      Ingestion orchestrator
│   │   ├── retriever_dense.py   pgvector cosine
│   │   ├── retriever_sparse.py  tsvector BM25 + HybridRetriever RPC client
│   │   ├── fusion.py            Reciprocal Rank Fusion
│   │   ├── reranker.py          Cohere + local cross-encoder
│   │   ├── generator.py         gpt-4o generation + streaming
│   │   ├── citation_resolver.py [SOURCE_N] assembly + resolution
│   │   └── query_pipeline.py    embed → retrieve → rerank → guardrail
│   ├── models/                  schemas.py (Pydantic), database.py (Supabase clients)
│   └── utils/                   logger, token_counter, prompt_loader
├── prompts/
│   └── rag_generation_v1.yaml   default citation-enforced prompt
├── sql/
│   ├── admin/                   destructive manual reset SQL
│   ├── migrations/              versioned SQL up/down migrations
│   ├── schema.sql               legacy Phase 1 reference snapshot
│   ├── phase2_migration.sql     legacy Phase 2 reference snapshot
│   └── phase3_migration.sql     legacy Phase 3 reference snapshot
├── scripts/
│   ├── run-migrations.sh        local dbmate wrapper (up/rollback/status/new)
│   ├── reset-environment.sh     purge bucket then truncate DB
│   ├── truncate-all-tables.sh   destructive DB reset helper
│   └── purge-supabase-bucket.py destructive Storage reset helper
├── tests/                       37 tests (parser, chunker, embedder, pipeline, API, fusion, reranker, generator, citation resolver, prompt loader, query pipeline)
├── Dockerfile / docker-compose.yml
├── requirements.txt / pyproject.toml
└── .env.example
```

## Quickstart

```bash
# 1. Environment
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Required: SUPABASE_*, SUPABASE_DB_URL, OPENAI_API_KEY, LLAMA_CLOUD_API_KEY
# Phase 2:  COHERE_API_KEY (or set RERANKER_PROVIDER=local)
#           GENERATION_MODEL, GENERATION_TEMPERATURE, GENERATION_MAX_TOKENS
#           DENSE_TOP_N, SPARSE_TOP_N, RRF_K, RERANK_TOP_K, RELEVANCE_THRESHOLD

# Non-sensitive defaults are versioned in:
#   config/config.defaults.json
# You can override any of them via env vars or .env

# 3. Database migrations
#    Apply all pending migrations:
./scripts/run-migrations.sh up

# 4. Run
uvicorn app.main:app --reload --port 8000

# 5. Docker
docker compose up --build
```

`docker compose up --build` now runs the migration container first and only
starts the API after pending migrations succeed.

## Database Migrations

Schema changes are managed exclusively through versioned SQL migrations in
`sql/migrations/`. Do not apply `sql/schema.sql`, `sql/phase2_migration.sql`,
or `sql/phase3_migration.sql` directly in Supabase for normal development.

### Migration prerequisites

Add `SUPABASE_DB_URL` to `.env`. This must be a Postgres connection string,
not the REST API URL. Example shape:

```dotenv
SUPABASE_DB_URL=postgres://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
```

### Apply migrations locally

```bash
chmod +x scripts/run-migrations.sh
./scripts/run-migrations.sh up
```

The helper script will:

- Load `.env`
- Read `SUPABASE_DB_URL`
- Use a local `dbmate` install if available
- Fall back to the official `ghcr.io/amacneil/dbmate` container if Docker is installed

### Roll back the latest migration

```bash
./scripts/run-migrations.sh rollback
```

### Show migration status

```bash
./scripts/run-migrations.sh status
```

### Create a new migration

```bash
./scripts/run-migrations.sh new add_example_table
```

Every migration file must include both sections:

```sql
-- migrate:up
-- forward changes

-- migrate:down
-- rollback changes
```

### Docker startup behavior

`docker compose up --build` runs:

1. `migrate` service using `ghcr.io/amacneil/dbmate`
2. `dbmate --wait up` against `SUPABASE_DB_URL`
3. `api` service only after migrations complete successfully

## Admin Reset Scripts

Two destructive reset utilities are included for explicit operational use.
They are intentionally separate from `sql/migrations/` so they never run as
part of normal schema migration startup.

Before using any of these scripts:

- Confirm you are targeting the correct Supabase project
- Confirm `.env` points at the intended environment
- Treat these commands as destructive and non-routine

### Truncate all application tables

SQL source:

- [sql/admin/202604160101_truncate_all_tables.sql](sql/admin/202604160101_truncate_all_tables.sql)

Wrapper:

```bash
chmod +x scripts/truncate-all-tables.sh
./scripts/truncate-all-tables.sh --yes
```

Behavior:

- Loads `.env`
- Requires `SUPABASE_DB_URL`
- Executes the SQL file with `psql`
- Falls back to a disposable `postgres:16-alpine` container if `psql` is not installed
- Truncates `eval_sample_results`, `eval_runs`, `prompt_versions`, `documents`, `ingestion_jobs`, and `tenants`

Use this only in development, test, or carefully controlled admin workflows.

### Empty the Supabase Storage bucket

Storage deletion must go through the Supabase Storage API, not direct SQL.
Supabase explicitly warns that deleting storage objects via SQL can orphan
files in the bucket.

Script:

```bash
python scripts/purge-supabase-bucket.py --yes
```

Optional bucket override:

```bash
python scripts/purge-supabase-bucket.py --yes --bucket documents
```

Behavior:

- Loads `.env`
- Requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
- Uses `SUPABASE_STORAGE_BUCKET` by default
- Calls the official Supabase Storage API to empty the bucket

### Full environment reset

Wrapper:

```bash
chmod +x scripts/reset-environment.sh
./scripts/reset-environment.sh --yes
```

Behavior:

- Empties the configured Supabase Storage bucket first
- Truncates all application tables second
- Stops immediately if either step fails

Equivalent manual order:

1. `python3 scripts/purge-supabase-bucket.py --yes`
2. `./scripts/truncate-all-tables.sh --yes`

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

Tests use in-memory fakes for Supabase, OpenAI (sync + streaming), and the
reranker — no network, no real API keys, no Cohere/`sentence-transformers`
install required for the unit suite. See [tests/fakes.py](tests/fakes.py).

Suite: **37 tests** — parser, chunker, embedder, ingestion pipeline, API,
RRF fusion, reranker fallback, generator (sync + streaming), citation
resolver, prompt loader precedence, and end-to-end `/query`, `/query/stream`,
and `/prompts` round-trip.

## Metadata Schema

Every chunk in `documents.metadata` contains the full citation payload:

```json
{
  "source": "contract.pdf",
  "document_id": "uuid-of-parent",
  "page_number": 5,
  "bounding_boxes": [[72, 340, 540, 380]],
  "section_heading": "Section 3.2 — Liability",
  "document_title": "Master Services Agreement",
  "chunk_index": 12,
  "total_chunks": 45,
  "parser": "llamaparse",
  "chunk_strategy": "recursive_character",
  "chunk_size_tokens": 700,
  "overlap_tokens": 100
}
```

Missing values are stored as `null` — never dropped. The resolver preserves
all of this on every `Citation` returned from `/query`.

## Multi-Tenancy

- Ingestion runs with `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS).
- Client-facing reads use `anon`/`authenticated` keys; RLS policies in
  [sql/schema.sql](sql/schema.sql) and [sql/phase2_migration.sql](sql/phase2_migration.sql)
  filter on `tenant_id = auth.jwt() -> 'app_metadata' ->> 'organization_id'`.
- `match_documents` and `match_documents_hybrid` both accept
  `filter_tenant_id` for explicit server-side scoping — the `query_pipeline`
  always passes the JWT-resolved tenant, so the LLM never sees cross-tenant
  chunks.
- `prompt_versions` supports tenant-specific overrides (`tenant_id = <uuid>`)
  alongside global prompts (`tenant_id IS NULL`); the loader prefers the
  tenant row when both exist.

## Prompt Management

Prompts are versioned in `prompt_versions` with audit-friendly history: every
new `POST /prompts` creates a new row, the previous active row for the same
`(tenant_id, name)` is deactivated, and deactivated prompts are never
deleted. Local development can skip the database entirely — the loader falls
back to `prompts/<name>.yaml`. The default prompt ships as
[prompts/rag_generation_v1.yaml](prompts/rag_generation_v1.yaml).

YAML prompts can reference centralized settings using `${setting_name}`. Example:

```yaml
model: ${generation_model}
temperature: ${generation_temperature}
max_tokens: ${generation_max_tokens}
```

Those values are resolved through the same settings chain above, so prompt
files can stay declarative without duplicating non-sensitive defaults.

The system prompt hard-constrains the LLM to the provided context, requires
`[SOURCE_N]` anchors on every factual claim, and mandates an exact decline
message when the context is insufficient — this is the second layer of
hallucination defense on top of the relevance-threshold short-circuit.

## Phase 1 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Working ingestion pipeline | Done |
| 2 | Supabase pgvector schema + RLS + HNSW | Done (apply via SQL editor) |
| 3 | Chunk + embedding storage with metadata | Done |
| 4 | Retrieval via `match_documents` | Done |
| 5 | REST API (`/ingest`, `/status`, `/query`, `/health`) | Done |
| 6 | Multi-tenant isolation | Done (RLS + `tenant_id` on every row) |
| 7 | Test suite | Done |
| 8 | Docker-ready deployment | Done |

## Phase 2 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Full-text search column + GIN index | Done ([sql/phase2_migration.sql](sql/phase2_migration.sql)) |
| 2 | `match_documents_hybrid` RRF function | Done |
| 3 | Cross-encoder reranking (Cohere + local fallback) | Done |
| 4 | Citation-enforced generation (`[SOURCE_N]` anchors resolved to metadata) | Done |
| 5 | Hallucination guardrails (relevance threshold + prompt-based decline) | Done |
| 6 | Updated `/query` endpoint (embed → hybrid → rerank → generate → cite) | Done |
| 7 | Streaming `/query/stream` (SSE with up-front `sources` event) | Done |
| 8 | Prompt management (`/prompts` + YAML fallback) | Done |
| 9 | Per-step latency tracking in response metadata | Done |
| 10 | Phase 2 test suite (fusion, reranker, generator, citation resolver, E2E) | Done |

Phases 3–4 (Ragas evaluation, CI quality gates, AI SDK / chat widget, PDF
viewer with bbox overlays) remain out of scope — see [SPEC.md](SPEC.md) §16.
