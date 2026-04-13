# RAGfier — Phase 1 Ingestion Pipeline

Multi-tenant RAG ingestion backbone: parses PDFs/Markdown with layout-aware
extraction, chunks with situated context, embeds via OpenAI, and stores
citation-ready vectors in Supabase `pgvector` with Row-Level Security.

See [SPEC.md](SPEC.md) for the full technical spec and [AGENTS.md](AGENTS.md)
for the coding conventions and architectural constraints.

## Architecture

```
Upload → Supabase Storage → LlamaParse → Chunker → OpenAI Embeddings → pgvector
```

- **Parser** — [app/pipeline/parser.py](app/pipeline/parser.py): LlamaParse for PDFs, in-process Markdown parser. Tracks section headings and spatial metadata.
- **Chunker** — [app/pipeline/chunker.py](app/pipeline/chunker.py): `RecursiveCharacterTextSplitter`, 700-token target / 100 overlap, tiktoken `cl100k_base`. Prepends document title + section heading to every chunk.
- **Embedder** — [app/pipeline/embedder.py](app/pipeline/embedder.py): OpenAI `text-embedding-3-small` (1536d), batch size 100, exponential backoff (max 3 retries).
- **Upserter** — [app/pipeline/upserter.py](app/pipeline/upserter.py): Batch insert into `documents` with full metadata JSONB; updates `ingestion_jobs.status` at every step.
- **Orchestrator** — [app/pipeline/orchestrator.py](app/pipeline/orchestrator.py): Coordinates the full parse → chunk → embed → upsert flow under a single `job_id`.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/ingest` | Upload a PDF or Markdown file; returns `job_id` |
| `GET`  | `/status/{job_id}` | Poll pipeline progress |
| `POST` | `/query` | Natural-language retrieval (cosine similarity) |
| `GET`  | `/health` | Service health check |

All tenant-scoped endpoints require `Authorization: Bearer <jwt>` where the
JWT contains `app_metadata.organization_id`. An `X-Tenant-Id` header override
is accepted for local testing.

## Project Layout

```
RAGfier/
├── app/
│   ├── main.py                  FastAPI app + lifespan
│   ├── config.py                Pydantic Settings (env)
│   ├── api/                     /ingest, /status, /query, /health, auth dep
│   ├── pipeline/                parser, chunker, embedder, upserter, orchestrator
│   ├── models/                  schemas.py (Pydantic), database.py (Supabase clients)
│   └── utils/                   logger (structured JSON), token_counter (tiktoken)
├── sql/schema.sql               Full DB schema — run in Supabase SQL Editor
├── tests/                       17 tests covering parser, chunker, embedder, pipeline, API
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
cp .env.example .env   # fill in SUPABASE_*, OPENAI_API_KEY, LLAMA_CLOUD_API_KEY

# 3. Database
#    Open Supabase SQL Editor and run sql/schema.sql

# 4. Run
uvicorn app.main:app --reload --port 8000

# 5. Docker
docker compose up --build
```

## Testing

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
```

Tests use in-memory fakes for Supabase and OpenAI — no network or real keys
required. See [tests/fakes.py](tests/fakes.py).

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

Missing values are stored as `null` — never dropped.

## Multi-Tenancy

- Pipeline runs with `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS).
- Client-facing reads use `anon`/`authenticated` keys; RLS policies in
  [sql/schema.sql](sql/schema.sql) filter on
  `tenant_id = auth.jwt() -> 'app_metadata' ->> 'organization_id'`.
- Retrieval via the `match_documents` RPC accepts `filter_tenant_id` for
  explicit server-side scoping.

## Phase 1 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Working ingestion pipeline | Done |
| 2 | Supabase pgvector schema + RLS + HNSW | Done (apply via SQL editor) |
| 3 | Chunk + embedding storage with metadata | Done |
| 4 | Retrieval via `match_documents` | Done |
| 5 | REST API (`/ingest`, `/status`, `/query`, `/health`) | Done |
| 6 | Multi-tenant isolation | Done (RLS + `tenant_id` on every row) |
| 7 | Test suite | Done (17 tests) |
| 8 | Docker-ready deployment | Done |

Phases 2–4 (hybrid search, reranking, evaluation, SDK) are intentionally
out of scope for this iteration — see SPEC.md §14.
