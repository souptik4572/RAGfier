# AGENTS.md — RAG Ingestion Pipeline (Phase 1)

## Project Overview

This is a production-grade, multi-tenant RAG (Retrieval-Augmented Generation) ingestion pipeline. It parses domain-specific documents (PDFs, Markdown), chunks them semantically, generates embeddings, and stores them in Supabase pgvector with citation-ready spatial metadata. The system is designed for eventual SaaS deployment with tenant isolation via Row-Level Security.

## Tech Stack

- **Language**: Python 3.10+
- **API**: FastAPI (async throughout — never use sync endpoints)
- **Orchestration**: LangChain / LangGraph
- **Parsing**: LlamaParse (layout-aware PDF extraction)
- **Embeddings**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **Database**: Supabase PostgreSQL + pgvector
- **File Storage**: Supabase Storage

## Build & Run

```bash
# Clone and setup
git clone <repo-url>
cd rag-ingestion

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in keys
cp .env.example .env

# Run database migrations
# Execute sql/schema.sql in the Supabase SQL Editor (not via CLI)

# Start the dev server
uvicorn app.main:app --reload --port 8000

# Run with Docker
docker-compose up --build
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_parser.py -v
pytest tests/test_chunker.py -v
pytest tests/test_embedder.py -v
pytest tests/test_pipeline.py -v
pytest tests/test_api.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing
```

All tests must pass before any commit. If you add or modify a module, add or update corresponding tests in `tests/`.

## Project Structure

rag-ingestion/
├── app/
│   ├── main.py                  # FastAPI app init, middleware, lifespan
│   ├── config.py                # Pydantic Settings — all env vars here
│   ├── api/
│   │   ├── ingest.py            # POST /ingest
│   │   ├── status.py            # GET /status/{job_id}
│   │   ├── query.py             # POST /query
│   │   └── health.py            # GET /health
│   ├── pipeline/
│   │   ├── orchestrator.py      # Coordinates parse → chunk → embed → store
│   │   ├── parser.py            # LlamaParse wrapper
│   │   ├── chunker.py           # Recursive character splitter
│   │   ├── embedder.py          # OpenAI batch embedding
│   │   └── upserter.py          # Supabase bulk insert
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── database.py          # Supabase client singleton
│   └── utils/
│       ├── token_counter.py     # tiktoken-based counting (cl100k_base)
│       └── logger.py            # Structured JSON logging
├── sql/
│   └── schema.sql               # Full DB schema — run in Supabase SQL Editor
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── SPEC.md

## Coding Conventions

### Python Style

- Use `async def` for all FastAPI endpoints and any I/O-bound functions.
- Type-hint every function signature. Use `from __future__ import annotations` at the top of every file.
- Use Pydantic `BaseModel` for all request/response schemas — never use raw dicts at API boundaries.
- Imports: stdlib first, then third-party, then local. Use absolute imports (`from app.pipeline.parser import ...`), never relative imports.
- Naming: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.
- Keep functions under 50 lines. If a function is growing, extract a helper.

### Error Handling

- Never swallow exceptions silently. Always log with `logger.error()` including the `job_id` and `tenant_id` for traceability.
- Pipeline failures must update `ingestion_jobs.status` to `"failed"` and write a human-readable `error_message`.
- Use exponential backoff (max 3 retries) for external API calls (OpenAI, LlamaParse, Supabase).
- Raise `HTTPException` with appropriate status codes in API endpoints. Use 422 for validation errors, 404 for missing resources, 500 for unexpected failures.

### Logging

- Use the structured logger from `app/utils/logger.py`. Do not use `print()`.
- Every log line from the pipeline must include `job_id` and `tenant_id` as structured fields.
- Log at the start and end of each pipeline step (parsing, chunking, embedding, upserting) with duration.

## Architecture Constraints

### Multi-Tenancy — This Is Non-Negotiable

- **Every** record in the `documents` and `ingestion_jobs` tables must have a `tenant_id`.
- Never write a query that fetches documents without a tenant scope.
- The ingestion pipeline runs with the `service_role` key (bypasses RLS). Client-facing queries use `anon`/`authenticated` keys and RLS enforces isolation automatically.
- Tenant identity comes from `auth.jwt() -> 'app_metadata' ->> 'organization_id'` — do not invent a different mechanism.

### Embedding Pipeline

- Model is `text-embedding-3-small` (1536 dims). Do not switch models without updating the `VECTOR(1536)` column and HNSW index.
- Batch embeddings in groups of 100. The OpenAI API supports up to 2048 inputs per call, but 100 keeps latency predictable and retries cheap.
- Use `tiktoken` with the `cl100k_base` encoding for all token counting. Do not estimate tokens from character counts.

### Chunking Rules

- Target chunk size: 600–800 tokens. Overlap: 100 tokens.
- Separators in priority order: `["\n\n", "\n", ". ", " "]`. Split at the highest-level boundary first.
- Every chunk must be prepended with situated context: document title and section heading. This is critical for embedding quality — without it, retrieval degrades significantly.
- Preserve bounding box coordinates and page numbers from the parser. If spatial metadata is missing for a chunk, log a warning but do not skip the chunk.

### Metadata Schema

Every chunk stored must include this metadata structure (JSONB):

```json
{
  "source": "filename.pdf",
  "document_id": "uuid",
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

Do not omit fields. If a value is unavailable, set it to `null` — never drop the key.

## Database

- Schema lives in `sql/schema.sql`. Apply changes via the Supabase SQL Editor, not through an ORM migration tool.
- The `documents` table uses an HNSW index with `vector_cosine_ops`. Do not change the index type without benchmarking.
- The `match_documents` RPC function handles retrieval. Call it via `supabase.rpc("match_documents", {...})`.
- If you need to add columns to `documents`, also update the metadata JSONB schema and the Pydantic models in `app/models/schemas.py`.

## Environment Variables

All env vars are managed in `app/config.py` via Pydantic `Settings`. Never read `os.environ` directly elsewhere.

Required variables (see `.env.example`):

SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
OPENAI_API_KEY
LLAMA_CLOUD_API_KEY

## Security Rules

- Never commit `.env` or any file containing API keys. The `.gitignore` already excludes these.
- Never log API keys, tokens, or embedding vectors. Log chunk counts and metadata, not content.
- Never expose the `service_role` key to the client. It exists only in server-side environment variables.
- File uploads are validated for type (PDF, MD only) and size (max 50MB). Do not bypass these checks.
- Signed URLs for Supabase Storage expire after 1 hour. Do not increase this without discussion.

## Git Workflow

- Branch naming: `feature/<short-description>`, `fix/<short-description>`, `chore/<short-description>`.
- Commit messages: imperative mood, under 72 characters. Example: `Add batch retry logic to embedder module`.
- Every PR must have passing tests. Do not merge with test failures.
- Keep PRs focused on one concern. Do not bundle unrelated changes.

## Domain Vocabulary

| Term                | Meaning in This Project                                                 |
|---------------------|-------------------------------------------------------------------------|
| Chunk               | A segment of document text (600-800 tokens) stored with its embedding   |
| Situated context    | Document title + section heading prepended to a chunk before embedding  |
| Bounding box        | `[x0, y0, x1, y1]` coordinates of text location on a PDF page          |
| Tenant              | An organization/customer; identified by `tenant_id` (UUID)             |
| Ingestion job       | A tracked process of uploading, parsing, chunking, embedding one file   |
| Golden dataset      | (Phase 3) Curated Q&A pairs for automated evaluation                   |
| RLS                 | Row-Level Security — Supabase/Postgres feature for tenant isolation     |
| HNSW                | Hierarchical Navigable Small World — the ANN index type used            |
| RRF                 | (Phase 2) Reciprocal Rank Fusion — merges dense + sparse search results |

## Common Pitfalls

- **Token counting with `len(text)`**: This counts characters, not tokens. Always use `tiktoken`. A 700-character string can be anywhere from 150 to 250 tokens depending on content.
- **Forgetting situated context**: If you skip prepending the title/section heading to chunks, retrieval quality drops because the embedding model has no structural context.
- **Missing `tenant_id`**: If a document record is inserted without `tenant_id`, it becomes invisible to all tenants via RLS but still occupies storage. The DB has a `NOT NULL` constraint, but verify in application code too.
- **LlamaParse rate limits**: The free tier has limits. Handle 429 responses with backoff. Check the `X-RateLimit-Remaining` header.
- **Large PDFs (100+ pages)**: These can produce 500+ chunks. The embedding step will be the bottleneck. Monitor `ingestion_jobs.processed_chunks` to ensure progress isn't stalled.
- **HNSW index rebuild**: After bulk-inserting a large number of chunks, the HNSW index may need to be rebuilt for optimal recall. This is a Supabase operational concern, not an application one.

## What's Coming (Do Not Build Yet)

These features are planned for later phases. Do not implement them now, but be aware they will integrate with the current pipeline:

- **Phase 2**: Hybrid search (BM25 + vector via RRF), cross-encoder reranking, citation enforcement in LLM responses.
- **Phase 3**: Automated evaluation pipeline with Ragas (faithfulness, answer relevance, context precision/recall), CI-gated quality thresholds.
- **Phase 4**: AI SDK with embeddable chat widget, PDF viewer with bounding box overlays, multi-deployment architecture (API, widget, iframe).

