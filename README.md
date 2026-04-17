# RAGfier — Hosted RAG API, Platform, and Evaluation Pipeline

Multi-tenant Retrieval-Augmented Generation backbone. Phase 1 ingests
PDFs/Markdown into Supabase `pgvector` with full citation metadata and
Row-Level Security. Phase 2 turns that index into a production-quality
query pipeline: hybrid retrieval (dense + sparse + RRF), cross-encoder
reranking, and citation-enforced LLM generation with hallucination
guardrails and SSE streaming. Phase 3 adds an automated evaluation
pipeline: versioned golden datasets, Ragas-based scoring, custom RAG
quality metrics, persisted evaluation history, `/eval` APIs, and a
GitHub Actions quality gate. Phase 4 adds the first hosted-platform
slice: API-key-based `/v1` APIs, knowledge bases, integrations, managed
connector records, audit/request logging, and a server SDK.

See [SPEC.md](SPEC.md) (Phase 3) and [SPEC_Phase1.md](SPEC_Phase1.md) for the
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

### Evaluation pipeline (Phase 3)

```
Golden Dataset → Live Query Pipeline → Ragas + Custom Metrics → Threshold Check → Reports + DB History + CI Gate
```

- **Golden dataset loader** — [eval/dataset.py](eval/dataset.py): loads versioned JSON datasets from [eval/datasets/](eval/datasets/) into typed `GoldenDataset` / `GoldenSample` objects.
- **Seed dataset** — [eval/datasets/golden_v1.0.0.json](eval/datasets/golden_v1.0.0.json): checked-in Phase 3 starter corpus with version metadata and sample changelog support via [eval/datasets/CHANGELOG.md](eval/datasets/CHANGELOG.md). This is a seed set of 14 samples, not yet the 50+ sample target from the spec.
- **Synthetic dataset generation** — [eval/generate.py](eval/generate.py): Ragas `TestsetGenerator` CLI that drafts tenant-specific samples from ingested chunks and writes them to a review-required JSON file.
- **Pipeline adapter** — [eval/pipeline_adapter.py](eval/pipeline_adapter.py): runs the real Phase 2 query flow per sample and captures answer text, citations, retrieved contexts, latency, rerank score, model, and prompt version.
- **Ragas runner** — [eval/ragas_runner.py](eval/ragas_runner.py): lazy, optional wrapper around Faithfulness, Answer Relevancy, Context Precision, and Context Recall using `gpt-4o-mini` by default.
- **Custom metrics** — [eval/metrics/](eval/metrics/): adds citation coverage, decline accuracy for unanswerable prompts, and latency compliance on top of the core Ragas metrics.
- **Thresholding + aggregation** — [eval/thresholds.py](eval/thresholds.py) and [eval/aggregator.py](eval/aggregator.py): combines per-sample scores into run-level pass/fail results using YAML-configured thresholds and a minimum passing-rate rule. `context_recall` and `latency_compliance` are currently warning-only in the default config.
- **Runner + reports** — [eval/run.py](eval/run.py) and [eval/report.py](eval/report.py): executes the full evaluation concurrently, persists results, and writes JSON + Markdown reports under [eval/reports/](eval/reports/).
- **Run history tools** — [eval/history.py](eval/history.py) and [eval/compare.py](eval/compare.py): CLI helpers for listing recent runs and comparing two runs side by side.

### Hosted platform (Phase 4)

```
Dashboard JWT Auth → Integrations + API Keys → /v1 Hosted API → KB-scoped Query/Ingestion → Audit + Usage Logs
```

- **Platform auth** — [app/api/platform_auth.py](app/api/platform_auth.py): resolves `Authorization: Bearer <api_key>` into `(tenant_id, integration_id, api_key_id)` and enforces per-key scopes such as `query:read`, `documents:write`, and `analytics:read`.
- **Dashboard platform management** — [app/api/platform.py](app/api/platform.py): JWT-authenticated control-plane endpoints for creating integrations, minting/revoking API keys, and listing platform credentials.
- **Hosted `/v1` API** — [app/api/public_v1.py](app/api/public_v1.py): API-key-authenticated knowledge base, document, connector, query, streaming query, job, usage, and audit-log routes.
- **Knowledge-base scoping** — [app/pipeline/query_pipeline.py](app/pipeline/query_pipeline.py), [app/pipeline/retriever_dense.py](app/pipeline/retriever_dense.py), and [app/pipeline/retriever_sparse.py](app/pipeline/retriever_sparse.py): retrieval is now scoped by both `tenant_id` and selected `knowledge_base_id(s)`.
- **Extended ingestion metadata** — [app/pipeline/orchestrator.py](app/pipeline/orchestrator.py) and [app/pipeline/upserter.py](app/pipeline/upserter.py): ingestion records and document rows now carry `knowledge_base_id`, `source_type`, and `source_id`.
- **Platform security helpers** — [app/utils/platform_security.py](app/utils/platform_security.py): HMAC hashes API keys at rest and encrypts connector configuration blobs.
- **Observability helpers** — [app/utils/platform_observability.py](app/utils/platform_observability.py): writes `audit_logs` and `request_logs` rows for hosted operations.
- **Server SDK** — [sdk/python/ragfier_sdk.py](sdk/python/ragfier_sdk.py): async SDK client for `/v1/query`, `/v1/query/stream`, uploads, job polling, KB listing, and connector sync triggers.

## API Endpoints

### Auth and tenant-scoping matrix

| Method | Path | Auth mode | Tenant scope source | Purpose |
|--------|------|-----------|---------------------|---------|
| `POST` | `/auth/signup` | Public (no auth) | N/A | Create tenant + user and return JWT |
| `POST` | `/auth/login` | Public (no auth) | N/A | Login and return JWT |
| `GET`  | `/health` | Public (no auth) | N/A | Service health (Supabase, OpenAI, Cohere) |
| `POST` | `/platform/integrations` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Create a tenant-owned integration for hosted/API-key access |
| `GET`  | `/platform/integrations` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | List integrations for the authenticated tenant |
| `POST` | `/platform/api-keys` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Create a per-integration API key; returns the secret once |
| `GET`  | `/platform/api-keys` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | List API keys for the authenticated tenant |
| `POST` | `/platform/api-keys/{api_key_id}/revoke` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Revoke an API key |
| `POST` | `/ingest` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Upload a PDF or Markdown file; returns `job_id` |
| `GET`  | `/status/{job_id}` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Poll pipeline progress |
| `POST` | `/query` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Hybrid retrieval → rerank → generation with resolved `[SOURCE_N]` citations |
| `POST` | `/query/stream` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Same pipeline, streamed as SSE: `sources` → `token`… → `done` |
| `POST` | `/eval/run` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Start an evaluation run for the authenticated tenant and dataset version |
| `GET`  | `/eval/runs` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | List recent evaluation runs for the authenticated tenant |
| `GET`  | `/eval/runs/{run_id}/samples` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Inspect per-sample results for a single evaluation run |
| `GET`  | `/prompts` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | List tenant + global prompt versions |
| `POST` | `/prompts` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT (or `X-Tenant-Id` for local testing) | Create a new prompt version (auto-deactivates the previous active one) |
| `POST` | `/v1/knowledge-bases` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Create a hosted knowledge base via API key |
| `GET`  | `/v1/knowledge-bases` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | List hosted knowledge bases available to the API key’s tenant |
| `POST` | `/v1/documents/upload` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Upload a document into a specific knowledge base |
| `GET`  | `/v1/documents` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | List uploaded documents/jobs for the API key’s tenant |
| `GET`  | `/v1/documents/{document_id}` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Fetch one document/job summary |
| `DELETE` | `/v1/documents/{document_id}` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Delete a document and its stored chunks |
| `POST` | `/v1/query` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Hosted KB-scoped query with request id and usage metadata |
| `POST` | `/v1/query/stream` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Hosted SSE query API |
| `POST` | `/v1/connectors/s3` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Create an S3 connector record |
| `POST` | `/v1/connectors/supabase` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Create a Supabase connector record |
| `POST` | `/v1/connectors/{id}/sync` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Create a manual connector sync job |
| `GET`  | `/v1/jobs/{job_id}` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | Poll a hosted ingestion job |
| `GET`  | `/v1/usage` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | List request-level usage rollups |
| `GET`  | `/v1/audit-logs` | API key (`Authorization: Bearer <api_key>`) | Tenant resolved from API key record | List hosted audit log entries |

JWT-protected endpoints derive tenant context from
`app_metadata.organization_id` in the bearer token. For local testing only,
you can override tenant resolution with `X-Tenant-Id`.

Hosted `/v1` endpoints never trust caller-provided tenant ids; tenant scope is
resolved from the API key record (`api_keys.tenant_id`) in the database.

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

### `/v1/query` response additions

Hosted queries return the same answer/citation payload as `/query`, plus:

- `request_id`: stable request identifier for auditing and support
- `usage`: token counts and an estimated cost field

Public request bodies accept `knowledge_base_ids`, `external_user_id`,
`session_id`, and `tags` for tenant-side attribution.

### `/eval` workflow

- `POST /eval/run` accepts a dataset version or path, pre-creates an `eval_runs` row, and schedules the evaluation in a background task.
- `GET /eval/runs` returns aggregate scores such as `faithfulness_avg`, `answer_relevancy_avg`, `citation_coverage_avg`, and pass/fail status for the tenant.
- `GET /eval/runs/{run_id}/samples` returns per-sample scores, responses, and failure reasons for drill-down debugging.

## Project Layout

```
RAGfier/
├── app/
│   ├── main.py                  FastAPI app + lifespan
│   ├── config.py                Pydantic Settings (Phase 1 + Phase 2 + Phase 3 + Phase 4)
│   ├── api/
│   │   ├── ingest.py            POST /ingest
│   │   ├── status.py            GET /status/{job_id}
│   │   ├── query.py             POST /query  (hybrid + rerank + generation)
│   │   ├── query_stream.py      POST /query/stream  (SSE)
│   │   ├── platform.py          JWT-authenticated integrations + API key management
│   │   ├── platform_auth.py     API key resolution + scope enforcement
│   │   ├── public_v1.py         Hosted /v1 API surface
│   │   ├── eval.py              POST /eval/run, GET /eval/runs, GET /eval/runs/{id}/samples
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
│   └── utils/                   logger, token_counter, prompt_loader, platform_security, platform_observability
├── eval/
│   ├── datasets/                versioned golden datasets + changelog
│   ├── config/thresholds.yaml   evaluation thresholds + blocking rules
│   ├── metrics/                 citation coverage, decline accuracy, latency compliance
│   ├── run.py                   evaluation runner CLI
│   ├── generate.py              synthetic dataset generation CLI
│   ├── history.py               list recent evaluation runs
│   ├── compare.py               compare two evaluation runs
│   ├── ragas_runner.py          Ragas metric wrapper
│   ├── pipeline_adapter.py      bridge to the production query pipeline
│   └── report.py                JSON + Markdown report writer
├── .github/workflows/
│   └── rag-evaluation.yml       CI quality gate for evaluation regressions
├── prompts/
│   └── rag_generation_v1.yaml   default citation-enforced prompt
├── sdk/
│   └── python/
│       └── ragfier_sdk.py       async hosted API client
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
├── tests/                       69 tests including hosted platform + SDK coverage
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
# Phase 3:  EVAL_DATASET_PATH, EVAL_THRESHOLDS_PATH, EVAL_LLM_JUDGE,
#           EVAL_FAITHFULNESS_LLM, EVAL_MAX_CONCURRENCY,
#           EVAL_LATENCY_BUDGET_MS, EVAL_REPORTS_DIR
# Phase 4:  PLATFORM_API_KEY_SECRET, PLATFORM_ENCRYPTION_KEY,
#           PLATFORM_API_KEY_PREFIX, PLATFORM_DEFAULT_BASE_URL

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

## Docker

Use Docker when you want the API and migration runner to start together.

### Prerequisites

- Docker Desktop or Docker Engine with `docker compose`
- A populated `.env` file based on `.env.example`
- A valid `SUPABASE_DB_URL` Postgres connection string

### Required `.env` values

At minimum, set:

```dotenv
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_DB_URL=postgresql://postgres:<url-encoded-password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_ANON_KEY=...
OPENAI_API_KEY=...
LLAMA_CLOUD_API_KEY=...
```

If your database password contains special characters such as `@`, `:`, `/`,
`?`, or `#`, URL-encode the password before placing it in `SUPABASE_DB_URL`.

### Start the stack

```bash
docker compose up --build
```

What happens:

1. Docker builds the `api` image
2. The `migrate` service validates `SUPABASE_DB_URL`
3. Pending SQL migrations in `sql/migrations/` are applied
4. The FastAPI app starts on `http://localhost:8000`

### Start in the background

```bash
docker compose up --build -d
```

### View logs

```bash
docker compose logs -f
```

To follow only the API logs:

```bash
docker compose logs -f api
```

### Stop the stack

```bash
docker compose down
```

### Rebuild after Dockerfile or dependency changes

```bash
docker compose up --build --force-recreate
```

### Common Docker gotchas

- Do not use `localhost`, `127.0.0.1`, or `::1` inside `SUPABASE_DB_URL` for the containerized migration step
- For hosted Supabase, use `db.<project-ref>.supabase.co`
- For a database running on your machine, use `host.docker.internal`

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
2. Validates `SUPABASE_DB_URL` inside the container and runs `dbmate up`
3. `api` service only after migrations complete successfully

### Troubleshooting Docker migrations

If you see an error like:

```text
Error: unable to connect to database: dial tcp [::1]:5432: connect: connection refused
```

that usually means the migration container did not receive a usable
`SUPABASE_DB_URL`, so `dbmate` fell back to `localhost` inside Docker.

Check these exactly:

1. `.env` contains `SUPABASE_DB_URL=postgres://...`
2. The hostname inside `SUPABASE_DB_URL` is not `localhost`, `127.0.0.1`, or `::1`
3. For hosted Supabase, use the project Postgres host like `db.<project-ref>.supabase.co`
4. For a database running on your machine, use `host.docker.internal` instead of `localhost`

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
deepeval test run tests/test_rag_evaluation.py --verbose
```

Tests use in-memory fakes for Supabase, OpenAI (sync + streaming), and the
reranker — no network, no real API keys, no Cohere/`sentence-transformers`
install required for the unit suite. The DeepEval suite is separate and
intended for Phase 3 quality gating. See [tests/fakes.py](tests/fakes.py).

Suite: **69 tests** — parser, chunker, embedder, ingestion pipeline, API,
RRF fusion, reranker fallback, generator (sync + streaming), citation
resolver, prompt loader precedence, evaluation runner/API/custom metrics,
hosted platform auth, `/v1` knowledge bases/documents/connectors/query,
SDK coverage, and end-to-end `/query`, `/query/stream`, and `/prompts`
round-trip.

## Phase 3 Evaluation Workflow

### What is implemented

- Versioned golden dataset support via [eval/datasets/golden_v1.0.0.json](eval/datasets/golden_v1.0.0.json).
- Ragas-based scoring for faithfulness, answer relevancy, context precision, and context recall.
- Custom evaluation metrics for citation coverage, decline accuracy, and latency compliance.
- Threshold-based pass/fail aggregation with YAML config in [eval/config/thresholds.yaml](eval/config/thresholds.yaml).
- Persisted evaluation history in `eval_runs` and `eval_sample_results`, added by [sql/migrations/202604160003_phase3_eval_pipeline.sql](sql/migrations/202604160003_phase3_eval_pipeline.sql).
- Tenant-scoped evaluation APIs in [app/api/eval.py](app/api/eval.py).
- CLI entry points for running, generating, listing, and comparing evaluation runs.
- GitHub Actions workflow in [.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml).
- Unit and integration coverage for the Phase 3 pieces in [tests/test_eval_runner.py](tests/test_eval_runner.py), [tests/test_eval_api.py](tests/test_eval_api.py), [tests/test_custom_metrics.py](tests/test_custom_metrics.py), and [tests/test_rag_evaluation.py](tests/test_rag_evaluation.py).

### Metrics and thresholds

Thresholds live in [eval/config/thresholds.yaml](eval/config/thresholds.yaml) and are overridable per-env; `blocking: true` metrics fail the CI gate, `blocking: false` metrics only warn.

| Metric | What it measures | Source | Threshold | Blocking |
|--------|------------------|--------|-----------|----------|
| Faithfulness | Share of answer claims entailed by retrieved context | Ragas | ≥ 0.85 | Yes |
| Answer Relevancy | How on-topic the answer is vs. the user's question | Ragas | ≥ 0.80 | Yes |
| Context Precision | Whether relevant chunks are ranked above irrelevant ones | Ragas | ≥ 0.75 | Yes |
| Context Recall | Whether retrieval surfaced all info needed for the reference | Ragas | ≥ 0.75 | No (warn) |
| Citation Coverage | % of factual sentences carrying `[SOURCE_N]` anchors | Custom — [eval/metrics/citation_coverage.py](eval/metrics/citation_coverage.py) | ≥ 0.90 | Yes |
| Decline Accuracy | Correct decline on unanswerable / correct answer on answerable | Custom — [eval/metrics/decline_accuracy.py](eval/metrics/decline_accuracy.py) | ≥ 0.80 | Yes |
| Latency Compliance | % of queries completing within the configured budget | Custom — [eval/metrics/latency_compliance.py](eval/metrics/latency_compliance.py) | ≥ 0.90 | No (warn) |

Aggregation additionally enforces `min_passing_rate` (default 0.80) — at least that fraction of samples must pass every blocking metric for the run to pass. Defaults for the judge model and latency budget come from `EVAL_LLM_JUDGE` and `EVAL_LATENCY_BUDGET_MS`.

### Golden dataset shape

Golden datasets are versioned JSON under [eval/datasets/](eval/datasets/) with a [CHANGELOG.md](eval/datasets/CHANGELOG.md). Samples are typed as `GoldenSample` in [eval/dataset.py](eval/dataset.py) and expected to span six categories — `exact_match`, `conceptual`, `multi_context`, `unanswerable`, `reasoning`, `adversarial`. The spec targets ≥ 50 manually-reviewed samples; the checked-in `golden_v1.0.0.json` ships 14 seed samples and is expected to be extended via manual curation plus Ragas-generated drafts from [eval/generate.py](eval/generate.py) (synthetic samples must be human-reviewed before inclusion).

Never compare scores across dataset versions; every evaluation run records `dataset_version` alongside its aggregate scores.

### Storage schema

Added by [sql/migrations/202604160003_phase3_eval_pipeline.sql](sql/migrations/202604160003_phase3_eval_pipeline.sql):

- `eval_runs` — one row per evaluation run with `dataset_version`, `trigger`, `git_sha`, `git_branch`, aggregate averages for every metric, the thresholds used, `passed` + `failure_reasons`, `total_samples`, `failed_samples`, `eval_model`, `total_eval_cost_usd`, and `duration_seconds`.
- `eval_sample_results` — one row per sample per run with `user_input`, `response`, `retrieved_contexts`, `reference`, per-metric scores, latency, chunks retrieved, top rerank score, model used, and prompt version.
- Indexes on `(tenant_id, created_at DESC)` and `git_sha` on `eval_runs`, and on `eval_run_id` on `eval_sample_results`.
- RLS enforces `tenant_id = auth.jwt() -> 'app_metadata' ->> 'organization_id'` on both tables.

### Local commands

```bash
# Run the evaluation runner against the default dataset
python3 -m eval.run --tenant-id <tenant-uuid>

# Run against a specific dataset file or version stem
python3 -m eval.run --tenant-id <tenant-uuid> --dataset golden_v1.0.0

# Generate a synthetic draft dataset from tenant documents
python3 -m eval.generate --tenant-id <tenant-uuid> --size 50

# List recent evaluation runs
python3 -m eval.history --tenant-id <tenant-uuid> --last 10

# Compare two runs
python3 -m eval.compare --run-a <run-uuid> --run-b <run-uuid>
```

### CI quality gate

- [.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml) runs on PRs that touch retrieval, query, prompt, SQL, eval, or evaluation-test files.
- The workflow runs Phase 3 unit tests first, then `deepeval test run tests/test_rag_evaluation.py`.
- Evaluation reports are uploaded as artifacts when present, and CI includes a post-processing step that attempts to attach git metadata to the latest stored run.

### Current scope boundary

- Phase 3 remains an offline evaluation and CI-gating system.
- The checked-in dataset is still a seed corpus; the README does not claim the full 50+ manually reviewed golden set target has been reached yet.
- Phase 4 now includes the hosted backend/API-key layer, but not a full dashboard UI, durable background workers for connector execution, browser/widget delivery, or PDF overlay UX yet.

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
  `filter_tenant_id` and now support optional knowledge-base filters for
  explicit server-side scoping — the query pipeline always passes the
  resolved tenant, so the LLM never sees cross-tenant chunks.
- `prompt_versions` supports tenant-specific overrides (`tenant_id = <uuid>`)
  alongside global prompts (`tenant_id IS NULL`); the loader prefers the
  tenant row when both exist.
- Hosted `/v1` routes do not accept caller-controlled tenant identifiers.
  Tenant scope is derived from the API key record, which also ties every
  public request to an `integration_id` and `api_key_id`.

## Hosted Platform

Phase 4 introduces the first hosted control-plane and public API layer.

### Data model additions

- `knowledge_bases`: tenant-owned logical collections for retrieval and ingestion
- `integrations`: named app installations or environments under a tenant
- `api_keys`: per-integration keys with hashed secrets, scopes, expiry, status, and last-used timestamps
- `connector_sources`: tenant-owned S3 or Supabase connector definitions with encrypted config blobs
- `connector_sync_jobs`: manual sync jobs for connectors
- `audit_logs`: actor/resource/action trail for hosted operations
- `request_logs`: request-level usage and latency events
- `usage_rollups`: aggregation target for operational analytics

### Security model

- Dashboard operators continue using JWT auth
- Hosted SDK/API consumers use per-integration API keys
- API keys are hashed at rest and only returned once on creation
- Connector configs are encrypted before persistence
- Public routes enforce per-key scopes such as `kb:read`, `documents:write`, `query:read`, and `analytics:read`

### Current connector status

- `POST /v1/connectors/s3` and `POST /v1/connectors/supabase` create managed source records
- `POST /v1/connectors/{id}/sync` creates a manual sync job
- External crawling/fetching workers are not implemented yet; this is the hosted schema/API foundation

### Python SDK example

```python
import asyncio

from sdk.python.ragfier_sdk import RagfierSDK


async def main() -> None:
    client = RagfierSDK(
        api_key="rag_pk_xxxx.your-secret",
        base_url="http://localhost:8000",
    )
    try:
        response = await client.query(
            query="What is the liability cap?",
            knowledge_base_ids=["<knowledge-base-uuid>"],
            match_count=5,
        )
        print(response["answer"])
    finally:
        await client.aclose()


asyncio.run(main())
```

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

## Phase 3 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Golden dataset (v1.0.0) with versioned JSON + CHANGELOG | Done ([eval/datasets/golden_v1.0.0.json](eval/datasets/golden_v1.0.0.json), [eval/datasets/CHANGELOG.md](eval/datasets/CHANGELOG.md)) — seed of 14 samples; expanding toward the ≥50-sample target |
| 2 | Synthetic test generation pipeline | Done ([eval/generate.py](eval/generate.py)) — Ragas `TestsetGenerator` CLI writes a review-required draft; human review still mandatory before samples enter the golden set |
| 3 | Ragas evaluation pipeline (Faithfulness, Answer Relevancy, Context Precision, Context Recall) | Done ([eval/ragas_runner.py](eval/ragas_runner.py)) |
| 4 | Custom metrics (Citation Coverage, Decline Accuracy, Latency Compliance) | Done ([eval/metrics/](eval/metrics/)) |
| 5 | DeepEval pytest suite with pass/fail thresholds | Done ([tests/test_rag_evaluation.py](tests/test_rag_evaluation.py)) |
| 6 | GitHub Actions CI quality gate | Done ([.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml)) — triggers on PRs touching pipeline/prompt/SQL/eval paths, plus weekly cron |
| 7 | Evaluation storage schema (`eval_runs`, `eval_sample_results`) with RLS | Done ([sql/migrations/202604160003_phase3_eval_pipeline.sql](sql/migrations/202604160003_phase3_eval_pipeline.sql)) |
| 8 | `/eval/run`, `/eval/runs`, `/eval/runs/{id}/samples` APIs | Done ([app/api/eval.py](app/api/eval.py)) |
| 9 | CLI tools: `eval.run`, `eval.generate`, `eval.history`, `eval.compare` | Done ([eval/run.py](eval/run.py), [eval/generate.py](eval/generate.py), [eval/history.py](eval/history.py), [eval/compare.py](eval/compare.py)) |
| 10 | Historical score tracking + run comparison | Done — `eval.history` and `eval.compare` CLIs over the persisted `eval_runs` / `eval_sample_results` tables |
| 11 | Threshold configuration decoupled from code | Done ([eval/config/thresholds.yaml](eval/config/thresholds.yaml), [eval/thresholds.py](eval/thresholds.py)) |
| 12 | Phase 3 test coverage | Done ([tests/test_eval_runner.py](tests/test_eval_runner.py), [tests/test_eval_api.py](tests/test_eval_api.py), [tests/test_custom_metrics.py](tests/test_custom_metrics.py), [tests/test_rag_evaluation.py](tests/test_rag_evaluation.py)) |

## Phase 4 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Hosted `/v1` API with API-key auth | Done |
| 2 | JWT dashboard platform endpoints for integrations and API keys | Done |
| 3 | Knowledge-base abstraction and KB-scoped retrieval | Done |
| 4 | Request/audit logging tables and API exposure | Done |
| 5 | Connector source + sync job schema and APIs | Done (record/sync-job layer) |
| 6 | Python server SDK | Done |
| 7 | Secure API key hashing + encrypted connector config | Done |
| 8 | Full dashboard UI | Not yet implemented |
| 9 | Durable connector execution workers | Not yet implemented |
| 10 | Browser/widget delivery + PDF overlay UX | Not yet implemented |
