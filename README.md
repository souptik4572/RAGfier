# RAGfier — Hosted RAG API, Platform, and Evaluation Pipeline

Multi-tenant Retrieval-Augmented Generation backbone. Phase 1 ingests
PDFs/Markdown into Supabase `pgvector` with full citation metadata,
section-aware chunking, optional Anthropic-style per-chunk
contextualization with prompt caching, and Row-Level Security. Phase 2
turns that index into a production-quality query pipeline: hybrid
retrieval (dense + sparse + weighted RRF, OpenAI File-Search-style),
cross-encoder reranking, and citation-enforced LLM generation with
hallucination guardrails, grounded inference, and SSE streaming.
Phase 3 adds an automated evaluation pipeline: versioned golden
datasets, Ragas-based scoring, custom RAG quality metrics, persisted
evaluation history, `/eval` APIs, and a GitHub Actions quality gate.
Phase 4 adds the first hosted-platform slice: API-key-based `/v1`
APIs, knowledge bases, integrations, managed connector records,
audit/request logging, and a server SDK.

See [SPEC.md](SPEC.md) (Phase 3) and [SPEC_Phase1.md](SPEC_Phase1.md) for the
full technical specs, and [AGENTS.md](AGENTS.md) for coding conventions.

## Repository Layout

The repository is split into two top-level workspaces:

```
RAGfier/
├── backend/    FastAPI application, evaluation pipeline, SQL, scripts, SDK, tests
├── frontend/   Frontend application (placeholder — not yet implemented)
└── docker-compose.yml  Single multi-service compose file for the whole stack
```

All backend work lives under `backend/`. The frontend workspace is an empty
placeholder ready to receive a UI implementation that talks to the backend
through the existing REST/SSE APIs.

## Configuration Model

RAGfier uses a hybrid configuration model:

- **Sensitive values** (API keys, tokens, service-role credentials) live in environment variables / `backend/.env`.
- **Non-sensitive runtime defaults** live in [backend/config/config.defaults.json](backend/config/config.defaults.json) and are committed to source control.

Settings precedence (highest to lowest):

1. Explicit initialization values
2. Environment variables
3. `backend/.env`
4. JSON defaults file (`backend/config/config.defaults.json`)

This keeps deploy-time secrets out of source control while making safe defaults auditable and versioned.

## Architecture

### Ingestion (Phase 1)

```
Upload → Supabase Storage → LlamaParse → Chunker → Contextualizer (opt-in) → OpenAI Embeddings → pgvector
```

- **Parser** — [backend/app/pipeline/parser.py](backend/app/pipeline/parser.py): LlamaParse for PDFs, in-process Markdown parser. Tracks section headings and spatial metadata.
- **Chunker** — [backend/app/pipeline/chunker.py](backend/app/pipeline/chunker.py): `RecursiveCharacterTextSplitter`, 700-token target / 100 overlap, tiktoken `cl100k_base`. Section-aware: consecutive non-heading blocks sharing a `section_heading` and `page_number` are merged before splitting, so short enumerations (resume "Projects" / "Experience", contract paragraphs under one heading) stay in a single chunk — which is what lets superlative and cross-entry comparison queries succeed. Prepends document title + section heading to every chunk for situated context.
- **Contextualizer** — [backend/app/pipeline/contextualizer.py](backend/app/pipeline/contextualizer.py): Anthropic-style Contextual Retrieval ([Anthropic 2024](https://www.anthropic.com/news/contextual-retrieval)). When enabled, Claude Haiku (`claude-haiku-4-5-20251001` by default) generates a 50-100 token situated context per chunk using Anthropic prompt caching (`cache_control: ephemeral` on the `<document>` block), cutting input-token cost by ~90% on long documents. The summary is prepended as `[Context: ...]` ahead of the original chunk. Opt-in via `CONTEXTUALIZATION_ENABLED=true` + `ANTHROPIC_API_KEY`; disabled by default with graceful fall-back to the original chunk on any Anthropic error so the ingest pipeline never hard-fails on contextualization.
- **Embedder** — [backend/app/pipeline/embedder.py](backend/app/pipeline/embedder.py): OpenAI `text-embedding-3-small` (1536d), batch size 100, exponential backoff (max 3 retries).
- **Upserter** — [backend/app/pipeline/upserter.py](backend/app/pipeline/upserter.py): Batch insert into `documents` with full metadata JSONB; updates `ingestion_jobs.status` at every step.
- **Orchestrator** — [backend/app/pipeline/orchestrator.py](backend/app/pipeline/orchestrator.py): Coordinates the full parse → chunk → contextualize → embed → upsert flow under a single `job_id`, with a distinct `contextualizing` job-status step when the contextualizer is enabled.

### Query pipeline (Phase 2)

```
Query → Embed → Hybrid Retrieve (dense ∥ sparse ⇒ Weighted RRF) → Rerank → Guardrail → Prompt → LLM → Citations
```

- **Dense retrieval** — [backend/app/pipeline/retriever_dense.py](backend/app/pipeline/retriever_dense.py): cosine similarity via `match_documents` (HNSW + `vector_cosine_ops`).
- **Sparse retrieval** — [backend/app/pipeline/retriever_sparse.py](backend/app/pipeline/retriever_sparse.py): BM25-equivalent via Postgres `tsvector` + `websearch_to_tsquery` on a generated `fts` column. The `HybridRetriever` runs both branches + RRF inside the `match_documents_hybrid` SQL function, and auto-falls-back to an unweighted call on older databases that don't yet have the weighted RPC.
- **Reciprocal Rank Fusion (OpenAI-style weighted)** — [backend/app/pipeline/fusion.py](backend/app/pipeline/fusion.py) and [backend/sql/migrations/202604180005_weighted_hybrid_rrf.sql](backend/sql/migrations/202604180005_weighted_hybrid_rrf.sql): weighted RRF implementing the OpenAI "File Search" style formula `(semantic_weight / (k + dense_rank)) + (full_text_weight / (k + sparse_rank))`. Defaults of `SEMANTIC_WEIGHT=0.7` / `FULL_TEXT_WEIGHT=0.3` bias semantic search; tune toward lexical for keyword-heavy corpora (code, SKUs, identifiers). Passing `1.0 / 1.0` reproduces the classic unweighted RRF used by the fallback path.
- **Reranker** — [backend/app/pipeline/reranker.py](backend/app/pipeline/reranker.py): Cohere `rerank-english-v3.0` primary + local `cross-encoder/ms-marco-MiniLM-L-6-v2` fallback behind a single `Reranker` facade. Auto-falls-back on API failure and reports the provider actually used.
- **Hallucination guardrail** — [backend/app/pipeline/reranker.py](backend/app/pipeline/reranker.py): declines with the canonical "not enough information" message when the top rerank score is below `RELEVANCE_THRESHOLD`, or when retrieval is empty.
- **Generator** — [backend/app/pipeline/generator.py](backend/app/pipeline/generator.py): OpenAI `gpt-4o` (configurable) with retry-wrapped `generate()` and async `stream()`; model/temperature/max_tokens are pulled from the prompt config.
- **Citation resolver** — [backend/app/pipeline/citation_resolver.py](backend/app/pipeline/citation_resolver.py): `assemble_context()` injects `[SOURCE_N]` headers with document / section / page; `resolve_citations()` parses the generated text and returns `Citation` objects with full metadata and rerank/RRF scores.
- **Prompt loader** — [backend/app/utils/prompt_loader.py](backend/app/utils/prompt_loader.py): tenant-DB override > global-DB prompt > YAML file ([backend/prompts/rag_generation_v1.yaml](backend/prompts/rag_generation_v1.yaml)).
- **Query orchestrator** — [backend/app/pipeline/query_pipeline.py](backend/app/pipeline/query_pipeline.py): shared `prepare_query()` that runs embed → hybrid retrieve → rerank → guardrail → context assembly, returning a `PreparedQuery` reused by both the sync and streaming endpoints. Tracks per-step latency in `RetrievalMetadata.latency_ms`.

### Evaluation pipeline (Phase 3)

```
Golden Dataset → Live Query Pipeline → Ragas + Custom Metrics → Threshold Check → Reports + DB History + CI Gate
```

- **Golden dataset loader** — [backend/eval/dataset.py](backend/eval/dataset.py): loads versioned JSON datasets from [backend/eval/datasets/](backend/eval/datasets/) into typed `GoldenDataset` / `GoldenSample` objects.
- **Seed dataset** — [backend/eval/datasets/golden_v1.0.0.json](backend/eval/datasets/golden_v1.0.0.json): checked-in Phase 3 starter corpus with version metadata and sample changelog support via [backend/eval/datasets/CHANGELOG.md](backend/eval/datasets/CHANGELOG.md). This is a seed set of 14 samples, not yet the 50+ sample target from the spec.
- **Synthetic dataset generation** — [backend/eval/generate.py](backend/eval/generate.py): Ragas `TestsetGenerator` CLI that drafts tenant-specific samples from ingested chunks and writes them to a review-required JSON file.
- **Pipeline adapter** — [backend/eval/pipeline_adapter.py](backend/eval/pipeline_adapter.py): runs the real Phase 2 query flow per sample and captures answer text, citations, retrieved contexts, latency, rerank score, model, and prompt version.
- **Ragas runner** — [backend/eval/ragas_runner.py](backend/eval/ragas_runner.py): lazy, optional wrapper around Faithfulness, Answer Relevancy, Context Precision, and Context Recall using `gpt-4o-mini` by default.
- **Custom metrics** — [backend/eval/metrics/](backend/eval/metrics/): adds citation coverage, decline accuracy for unanswerable prompts, and latency compliance on top of the core Ragas metrics.
- **Thresholding + aggregation** — [backend/eval/thresholds.py](backend/eval/thresholds.py) and [backend/eval/aggregator.py](backend/eval/aggregator.py): combines per-sample scores into run-level pass/fail results using YAML-configured thresholds and a minimum passing-rate rule. `context_recall` and `latency_compliance` are currently warning-only in the default config.
- **Runner + reports** — [backend/eval/run.py](backend/eval/run.py) and [backend/eval/report.py](backend/eval/report.py): executes the full evaluation concurrently, persists results, and writes JSON + Markdown reports under [backend/eval/reports/](backend/eval/reports/).
- **Run history tools** — [backend/eval/history.py](backend/eval/history.py) and [backend/eval/compare.py](backend/eval/compare.py): CLI helpers for listing recent runs and comparing two runs side by side.

### Hosted platform (Phase 4)

```
Dashboard JWT Auth → Integrations + API Keys → /v1 Hosted API → Integration-scoped Query/Ingestion → Audit + Usage Logs
```

- **Platform auth** — [backend/app/api/platform_auth.py](backend/app/api/platform_auth.py): resolves `Authorization: Bearer <api_key>` into `(tenant_id, integration_id, api_key_id)` and enforces per-key scopes such as `query:read`, `documents:write`, and `analytics:read`.
- **Dashboard platform management** — [backend/app/api/platform.py](backend/app/api/platform.py): JWT-authenticated control-plane endpoints for creating integrations, minting/revoking API keys, and listing platform credentials.
- **Integration-scoped endpoints** — [backend/app/api/integrations.py](backend/app/api/integrations.py): JWT document upload/list and API-key query/stream endpoints scoped to a named integration (`/v1/integrations/{id}/...`).
- **Hosted `/v1` API** — [backend/app/api/public_v1.py](backend/app/api/public_v1.py): API-key-authenticated knowledge base, document, connector, flat integration query/stream, job, usage, and audit-log routes.
- **Integration resolver** — [backend/app/utils/integration_resolver.py](backend/app/utils/integration_resolver.py): resolves an explicit `integration_id` or falls back to the tenant's default global integration (auto-created on first use).
- **Integration scoping** — [backend/app/pipeline/query_pipeline.py](backend/app/pipeline/query_pipeline.py), [backend/app/pipeline/retriever_dense.py](backend/app/pipeline/retriever_dense.py), and [backend/app/pipeline/retriever_sparse.py](backend/app/pipeline/retriever_sparse.py): retrieval is scoped by `tenant_id` and `integration_id`.
- **Extended ingestion metadata** — [backend/app/pipeline/orchestrator.py](backend/app/pipeline/orchestrator.py) and [backend/app/pipeline/upserter.py](backend/app/pipeline/upserter.py): ingestion records and document rows carry `integration_id`, `source_type`, and `source_id`.
- **Platform security helpers** — [backend/app/utils/platform_security.py](backend/app/utils/platform_security.py): HMAC hashes API keys at rest and encrypts connector configuration blobs.
- **Observability helpers** — [backend/app/utils/platform_observability.py](backend/app/utils/platform_observability.py): writes `audit_logs` and `request_logs` rows for hosted operations.
- **Server SDK** — [backend/sdk/python/ragfier_sdk.py](backend/sdk/python/ragfier_sdk.py): async SDK client for `/v1/query`, `/v1/query/stream`, uploads, job polling, KB listing, and connector sync triggers.

## API Endpoints

### Auth and tenant-scoping matrix

| Method | Path | Auth mode | Tenant scope source | Purpose |
|--------|------|-----------|---------------------|---------|
| `POST` | `/auth/signup` | Public (no auth) | N/A | Create tenant + user, auto-provision default global integration, return JWT |
| `POST` | `/auth/login` | Public (no auth) | N/A | Login and return JWT |
| `GET`  | `/health` | Public (no auth) | N/A | Service health (Supabase, OpenAI, Cohere) |
| `POST` | `/platform/integrations` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Create a tenant-owned integration |
| `GET`  | `/platform/integrations` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | List integrations (always includes default global integration first) |
| `POST` | `/platform/api-keys` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Create a per-integration API key; secret returned once, stored as hash |
| `GET`  | `/platform/api-keys` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | List API keys for the authenticated tenant |
| `POST` | `/platform/api-keys/{api_key_id}/revoke` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Revoke an API key (idempotent; preserves audit history) |
| `POST` | `/ingest` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Upload a file; resolves integration from body field or tenant default |
| `GET`  | `/status/{job_id}` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Poll pipeline progress |
| `POST` | `/query` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Hybrid retrieval → rerank → generation; resolves integration from body or default |
| `POST` | `/query/stream` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Same pipeline, streamed as SSE: `sources` → `token`… → `done` |
| `POST` | `/v1/integrations/{integration_id}/documents` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Upload document into a named integration |
| `GET`  | `/v1/integrations/{integration_id}/documents` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | List documents in a named integration |
| `POST` | `/v1/integrations/{integration_id}/query` | API key (`Authorization: Bearer <api_key>`) | Tenant + integration resolved from API key | Query documents scoped to the named integration; key's integration must match path |
| `POST` | `/v1/integrations/{integration_id}/query/stream` | API key (`Authorization: Bearer <api_key>`) | Tenant + integration resolved from API key | SSE query scoped to the named integration; key must match |
| `POST` | `/v1/query/integration` | API key (`Authorization: Bearer <api_key>`) | Tenant + integration resolved from API key | Flat integration query; integration resolved from key |
| `POST` | `/v1/query/integration/stream` | API key (`Authorization: Bearer <api_key>`) | Tenant + integration resolved from API key | Flat integration SSE query; integration resolved from key |
| `POST` | `/eval/run` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Start an evaluation run |
| `GET`  | `/eval/runs` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | List recent evaluation runs |
| `GET`  | `/eval/runs/{run_id}/samples` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Inspect per-sample results for a single evaluation run |
| `GET`  | `/prompts` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | List tenant + global prompt versions |
| `POST` | `/prompts` | JWT (`Authorization: Bearer <jwt>`) | `app_metadata.organization_id` in JWT | Create a new prompt version |
| `POST` | `/v1/knowledge-bases` *(deprecated)* | API key | Tenant resolved from API key | Create a hosted knowledge base |
| `GET`  | `/v1/knowledge-bases` *(deprecated)* | API key | Tenant resolved from API key | List hosted knowledge bases |
| `POST` | `/v1/documents/upload` | API key | Tenant resolved from API key | Upload a document into a knowledge base |
| `GET`  | `/v1/documents` | API key | Tenant resolved from API key | List uploaded documents/jobs |
| `GET`  | `/v1/documents/{document_id}` | API key | Tenant resolved from API key | Fetch one document/job summary |
| `DELETE` | `/v1/documents/{document_id}` | API key | Tenant resolved from API key | Delete a document and its stored chunks |
| `POST` | `/v1/connectors/s3` *(deprecated)* | API key | Tenant resolved from API key | Create an S3 connector record |
| `POST` | `/v1/connectors/supabase` *(deprecated)* | API key | Tenant resolved from API key | Create a Supabase connector record |
| `POST` | `/v1/connectors/{id}/sync` *(deprecated)* | API key | Tenant resolved from API key | Create a manual connector sync job |
| `GET`  | `/v1/jobs/{job_id}` | API key | Tenant resolved from API key | Poll a hosted ingestion job |
| `GET`  | `/v1/usage` | API key | Tenant resolved from API key | List request-level usage rollups |
| `GET`  | `/v1/audit-logs` | API key | Tenant resolved from API key | List hosted audit log entries |

JWT-protected endpoints derive tenant context from
`app_metadata.organization_id` in the bearer token. For local testing only,
you can override tenant resolution with `X-Tenant-Id`.

Hosted `/v1` endpoints never trust caller-provided tenant ids; tenant scope is
resolved from the API key record (`api_keys.tenant_id`) in the database.

### Integration resolution order

Every endpoint that can target an integration resolves the final integration id
using this priority:

1. Path parameter `integration_id`
2. Body or form field `integration_id`
3. Tenant's default global integration (auto-created on first use if missing)

If the resolved integration does not belong to the authenticated tenant, the
request fails with `404` to avoid leaking whether another tenant's integration
exists.

### Authentication model

**Tenant JWT** — control-plane operations (signup, login, create/list
integrations, create/revoke API keys, upload documents, list jobs, eval runs,
prompts). The JWT must carry `app_metadata.organization_id`.

**Integration API key** — runtime query traffic. Sent as
`Authorization: Bearer <api_key>`. The key resolves `tenant_id`,
`integration_id`, `api_key_id`, and `scopes`. Recommended scopes:
`query:read`, `documents:read`, `documents:write`, `kb:read`, `kb:write`,
`analytics:read`.

Both query paths (`/query` JWT and `/v1/integrations/{id}/query` API key) run
the same retrieval and generation pipeline. Response shape, citation semantics,
guardrail behaviour, and retrieval metadata are materially equivalent across
both paths.

### Request and response shapes

#### `POST /auth/signup`

```json
// request
{
  "email": "user@example.com",
  "password": "secret-password",
  "tenant_name": "Acme Inc",
  "tenant_slug": "acme"
}

// response
{
  "message": "auth.signup_succeeded",
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "optional-refresh-token",
  "tenant_id": "uuid",
  "user_id": "uuid-or-null",
  "email": "user@example.com"
}
```

Signup creates the tenant row, the initial user, and the default global
integration before returning the JWT.

#### `POST /auth/login`

```json
// request
{ "email": "user@example.com", "password": "secret-password" }

// response
{
  "message": "auth.login_succeeded",
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "optional-refresh-token",
  "tenant_id": "uuid",
  "user_id": "uuid-or-null",
  "email": "user@example.com"
}
```

#### `POST /platform/integrations`

```json
// request
{
  "name": "Support Portal",
  "environment": "production",
  "metadata": { "product": "support" }
}

// response
{
  "message": "platform.integration_created",
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Support Portal",
  "environment": "production",
  "metadata": { "product": "support" },
  "created_at": "2026-04-17T10:30:00Z"
}
```

#### `GET /platform/integrations`

```json
{
  "message": "platform.integrations_listed",
  "integrations": [
    {
      "id": "uuid",
      "tenant_id": "uuid",
      "name": "Default",
      "environment": "production",
      "metadata": {},
      "created_at": "2026-04-17T10:00:00Z"
    }
  ]
}
```

The default global integration is always present and listed first.

#### `POST /platform/api-keys`

```json
// request
{
  "integration_id": "uuid",
  "name": "Prod query key",
  "scopes": ["query:read", "documents:read"],
  "expires_at": null
}

// response
{
  "message": "platform.api_key_created",
  "id": "uuid",
  "tenant_id": "uuid",
  "integration_id": "uuid",
  "name": "Prod query key",
  "prefix": "rk_live_1234",
  "secret": "full-secret-returned-once",
  "scopes": ["query:read", "documents:read"],
  "status": "active",
  "expires_at": null,
  "last_used_at": null,
  "created_at": "2026-04-17T10:35:00Z"
}
```

The `secret` is returned exactly once and stored only as an HMAC hash.

#### `POST /platform/api-keys/{api_key_id}/revoke`

```json
{
  "message": "platform.api_key_revoked",
  "id": "uuid",
  "tenant_id": "uuid",
  "integration_id": "uuid",
  "name": "Prod query key",
  "prefix": "rk_live_1234",
  "scopes": ["query:read", "documents:read"],
  "status": "revoked",
  "expires_at": null,
  "last_used_at": "2026-04-17T10:50:00Z",
  "created_at": "2026-04-17T10:35:00Z"
}
```

Revocation is idempotent. The record is retained for audit history.

#### `POST /ingest` · `POST /v1/integrations/{id}/documents`

`multipart/form-data` — `file` required, `integration_id` optional (form field),
`document_title` optional, `metadata` optional JSON string.

```json
// response
{
  "message": "platform.document_uploaded",
  "job_id": "uuid",
  "integration_id": "uuid",
  "status": "pending",
  "file_name": "contract.pdf"
}
```

The pipeline (parse → chunk → embed → upsert) runs asynchronously. Each file
produces exactly one ingestion job. `integration_id` is persisted on both the
job and every resulting document chunk.

#### `GET /v1/integrations/{id}/documents`

```json
{
  "message": "platform.documents_listed",
  "documents": [
    {
      "id": "job-or-document-id",
      "tenant_id": "uuid",
      "integration_id": "uuid",
      "file_name": "contract.pdf",
      "document_title": "Master Services Agreement",
      "source_type": "upload",
      "status": "completed",
      "chunk_count": 42,
      "created_at": "2026-04-17T10:40:00Z"
    }
  ]
}
```

#### `GET /v1/jobs/{job_id}` · `GET /status/{job_id}`

```json
{
  "message": "platform.job_fetched",
  "job_id": "uuid",
  "status": "embedding",
  "file_name": "contract.pdf",
  "total_chunks": 42,
  "processed_chunks": 18,
  "error_message": null,
  "created_at": "2026-04-17T10:40:00Z",
  "updated_at": "2026-04-17T10:42:00Z"
}
```

#### `POST /query` · `POST /v1/integrations/{id}/query` · `POST /v1/query/integration`

```json
// request
{
  "query": "What is the liability cap?",
  "integration_id": "uuid-or-omitted",
  "match_count": 8,
  "rerank": true,
  "include_sources": true,
  "prompt_name": "rag_generation_v1",
  "external_user_id": "end-user-123",
  "session_id": "session-abc",
  "tags": ["legal", "support"]
}

// response
{
  "message": "query.completed",
  "request_id": "uuid",
  "query": "What is the liability cap?",
  "answer": "The liability cap shall not exceed $1,000,000 [SOURCE_1]...",
  "citations": [
    {
      "source_id": "SOURCE_1",
      "chunk_id": "uuid",
      "content": "The liability cap shall not exceed...",
      "metadata": {
        "source": "contract.pdf",
        "page_number": 5,
        "bounding_boxes": [[72, 340, 540, 380]],
        "section_heading": "Section 3.2 — Limitation of Liability",
        "document_title": "Master Services Agreement"
      },
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
  "declined": false,
  "usage": {
    "input_tokens": 132,
    "output_tokens": 84,
    "total_tokens": 216,
    "estimated_cost_usd": 0.0124
  }
}
```

Query routing rules:

- `POST /query` with JWT and no `integration_id` → default global integration
- `POST /query` with JWT and explicit `integration_id` → that integration (must belong to tenant)
- `POST /v1/query/integration` with API key → key's own integration
- `POST /v1/integrations/{id}/query` with API key → named integration; key's integration must match the path id

#### `/query/stream` · `/v1/integrations/{id}/query/stream` · `/v1/query/integration/stream` SSE events

```
event: sources
data: {"citations": [...]}          ← emitted before generation begins

event: token
data: The

event: token
data:  liability
…
event: done
data: {"retrieval_metadata": {...}, "declined": false}
```

The `sources` event lets a frontend render citation cards while tokens stream
in. Declines emit a single synthetic `token` event followed by `done` with
`declined: true`.

All heavy work (integration resolution, embedding, retrieval, rerank, prompt
assembly) happens inside the SSE generator, so failures surface as an `error`
event followed by a terminal `done`, rather than a pre-stream HTTP 500:

```
event: error
data: {"message": "Query pipeline failed", "detail": "<exception text>"}

event: done
data: {"message": "Query stream generation failed", "declined": false}
```

#### Error response shape

```json
{
  "message": "platform_auth.invalid_api_key",
  "detail": "optional detail"
}
```

Common status codes: `400` malformed, `401` missing/invalid credential,
`403` insufficient scope, `404` not found, `413` file too large, `422`
validation error, `500` internal error.

Representative error message keys: `auth.missing_bearer_token`,
`auth.missing_organization_id`, `platform_auth.invalid_api_key`,
`platform_auth.insufficient_scope`, `platform.integration_not_found`,
`platform.document_not_found`, `ingest.file_too_large`, `query.pipeline_failed`.

### `/eval` API workflow

- `POST /eval/run` accepts a dataset version or path, pre-creates an `eval_runs` row, and schedules the evaluation in a background task.
- `GET /eval/runs` returns aggregate scores such as `faithfulness_avg`, `answer_relevancy_avg`, `citation_coverage_avg`, and pass/fail status for the tenant.
- `GET /eval/runs/{run_id}/samples` returns per-sample scores, responses, and failure reasons for drill-down debugging.

## Project Layout

```
RAGfier/
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI app + lifespan
│   │   ├── config.py                Pydantic Settings (all phases)
│   │   ├── cli/
│   │   │   └── purge_supabase_bucket.py  canonical storage-purge command
│   │   ├── api/
│   │   │   ├── auth.py              POST /auth/signup, /auth/login; JWT resolution
│   │   │   ├── ingest.py            POST /ingest  (JWT, integration-aware)
│   │   │   ├── status.py            GET /status/{job_id}
│   │   │   ├── query.py             POST /query  (JWT, resolves default integration)
│   │   │   ├── query_stream.py      POST /query/stream  (SSE, JWT)
│   │   │   ├── platform.py          JWT control-plane: integrations + API key management
│   │   │   ├── platform_auth.py     API key resolution + scope enforcement
│   │   │   ├── integrations.py      /v1/integrations/{id}/documents, /query, /query/stream
│   │   │   ├── public_v1.py         Hosted /v1 API surface (KB-centric + flat query endpoints)
│   │   │   ├── eval.py              POST /eval/run, GET /eval/runs, GET /eval/runs/{id}/samples
│   │   │   ├── prompts.py           GET/POST /prompts
│   │   │   └── health.py            GET /health
│   │   ├── pipeline/
│   │   │   ├── parser.py            LlamaParse + MD
│   │   │   ├── chunker.py           section-aware recursive character splitter
│   │   │   ├── contextualizer.py    Anthropic contextual retrieval (prompt-cached, opt-in)
│   │   │   ├── embedder.py          OpenAI batch embeddings
│   │   │   ├── upserter.py          Supabase batch upsert
│   │   │   ├── orchestrator.py      ingestion orchestrator
│   │   │   ├── retriever_dense.py   pgvector cosine (integration-scoped)
│   │   │   ├── retriever_sparse.py  tsvector BM25 + HybridRetriever (integration-scoped, weighted RRF)
│   │   │   ├── fusion.py            Reciprocal Rank Fusion (weighted + unweighted)
│   │   │   ├── reranker.py          Cohere + local cross-encoder
│   │   │   ├── generator.py         gpt-4o generation + streaming
│   │   │   ├── citation_resolver.py [SOURCE_N] assembly + resolution
│   │   │   └── query_pipeline.py    embed → retrieve → rerank → guardrail
│   │   ├── models/
│   │   │   ├── schemas.py           Pydantic request/response models
│   │   │   └── database.py          Supabase + OpenAI client singletons
│   │   └── utils/
│   │       ├── api_errors.py        error helpers
│   │       ├── integration_resolver.py  default-integration resolution + auto-creation
│   │       ├── logger.py            structured logging
│   │       ├── messages.py          i18n message keys
│   │       ├── platform_observability.py  audit + request log writers
│   │       ├── platform_security.py HMAC key hashing + config encryption
│   │       ├── prompt_loader.py     prompt loading with tenant override
│   │       └── token_counter.py     tiktoken wrapper
│   ├── eval/
│   │   ├── datasets/                versioned golden datasets + CHANGELOG.md
│   │   ├── config/thresholds.yaml   evaluation thresholds + blocking rules
│   │   ├── metrics/                 citation coverage, decline accuracy, latency compliance
│   │   ├── run.py                   evaluation runner CLI
│   │   ├── generate.py              synthetic dataset generation CLI
│   │   ├── history.py               list recent evaluation runs
│   │   ├── compare.py               compare two evaluation runs
│   │   ├── ragas_runner.py          Ragas metric wrapper
│   │   ├── pipeline_adapter.py      bridge to the production query pipeline
│   │   └── report.py                JSON + Markdown report writer
│   ├── config/
│   │   ├── config.defaults.json     non-sensitive runtime defaults
│   │   └── messages.json            API message keys
│   ├── prompts/
│   │   └── rag_generation_v1.yaml   default citation-enforced prompt
│   ├── sdk/
│   │   └── python/
│   │       └── ragfier_sdk.py       async hosted API client
│   ├── sql/
│   │   ├── admin/                   destructive manual reset SQL
│   │   ├── migrations/              versioned SQL up/down migrations (source of truth)
│   │   └── schema.sql               consolidated head snapshot (regenerated, not hand-edited)
│   ├── scripts/
│   │   ├── run-migrations.sh        local dbmate wrapper (up/rollback/status/new)
│   │   ├── dump-schema.sh           regenerate sql/schema.sql from the live DB
│   │   ├── reset-environment.sh     purge bucket then truncate DB
│   │   ├── truncate-all-tables.sh   destructive DB reset helper
│   │   └── purge-supabase-bucket.py backward-compatible wrapper for package CLI
│   ├── tests/                       76 tests — all unit and integration coverage
│   ├── Dockerfile                   backend container image
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── .env.example
├── frontend/                        Frontend workspace (placeholder)
│   └── .gitkeep
├── docker-compose.yml               Multi-service compose: migrate + backend + frontend stub
└── README.md
```

## Quickstart

```bash
# 1. Clone and enter the backend workspace
cd backend

# 2. Environment
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Required: SUPABASE_*, SUPABASE_DB_URL, OPENAI_API_KEY, LLAMA_CLOUD_API_KEY
# Phase 2:  COHERE_API_KEY (or set RERANKER_PROVIDER=local)
#           GENERATION_MODEL, GENERATION_TEMPERATURE, GENERATION_MAX_TOKENS
#           DENSE_TOP_N, SPARSE_TOP_N, RRF_K, RERANK_TOP_K, RELEVANCE_THRESHOLD
#           SEMANTIC_WEIGHT, FULL_TEXT_WEIGHT   (OpenAI-style weighted RRF)
# Phase 2+: ANTHROPIC_API_KEY, CONTEXTUALIZATION_ENABLED,
#           CONTEXTUALIZER_MODEL, CONTEXTUALIZER_MAX_TOKENS,
#           CONTEXTUALIZER_MAX_CONCURRENCY, CONTEXTUALIZER_MAX_DOC_CHARS
#           (opt-in Anthropic contextual retrieval with prompt caching)
# Phase 3:  EVAL_DATASET_PATH, EVAL_THRESHOLDS_PATH, EVAL_LLM_JUDGE,
#           EVAL_FAITHFULNESS_LLM, EVAL_MAX_CONCURRENCY,
#           EVAL_LATENCY_BUDGET_MS, EVAL_REPORTS_DIR
# Phase 4:  PLATFORM_API_KEY_SECRET, PLATFORM_ENCRYPTION_KEY,
#           PLATFORM_API_KEY_PREFIX, PLATFORM_DEFAULT_BASE_URL

# Non-sensitive defaults are versioned in:
#   backend/config/config.defaults.json
# You can override any of them via env vars or .env

# 4. Database migrations (run from backend/)
./scripts/run-migrations.sh up

# 5. Run
uvicorn app.main:app --reload --port 8000

# 6. Docker (from repo root)
cd ..
docker compose up --build
```

`docker compose up --build` runs the migration container first and only
starts the backend after pending migrations succeed.

## Docker

Use Docker when you want the API and migration runner to start together.

### Prerequisites

- Docker Desktop or Docker Engine with `docker compose`
- A populated `backend/.env` file based on `backend/.env.example`
- A valid `SUPABASE_DB_URL` Postgres connection string

### Required `backend/.env` values

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

1. Docker builds the `backend` image from `backend/Dockerfile`
2. The `migrate` service validates `SUPABASE_DB_URL`
3. Pending SQL migrations in `backend/sql/migrations/` are applied
4. The FastAPI app starts on `http://localhost:8000`

### Start in the background

```bash
docker compose up --build -d
```

### View logs

```bash
docker compose logs -f
```

To follow only the backend logs:

```bash
docker compose logs -f backend
```

### Stop the stack

```bash
docker compose down
```

### Rebuild after Dockerfile or dependency changes

```bash
docker compose up --build --force-recreate
```

### Frontend service

The `frontend` service is defined but commented out in `docker-compose.yml`.
Once the frontend is implemented under `frontend/`, uncomment that block and
fill in the correct `build.dockerfile` path. The stub is pre-wired with:

```yaml
environment:
  - NEXT_PUBLIC_API_URL=http://backend:8000
depends_on:
  - backend
```

### Common Docker gotchas

- Do not use `localhost`, `127.0.0.1`, or `::1` inside `SUPABASE_DB_URL` for the containerised migration step
- For hosted Supabase, use `db.<project-ref>.supabase.co`
- For a database running on your machine, use `host.docker.internal`

## Database Migrations

Schema changes are managed exclusively through versioned SQL migrations in
`backend/sql/migrations/`. `backend/sql/schema.sql` is a consolidated head
snapshot that mirrors the current database after every migration has been
applied — it exists for code review, onboarding, and drift detection, and is
regenerated by `./scripts/dump-schema.sh` (never hand-edited). Do not apply
`backend/sql/schema.sql` directly in Supabase.

All migration commands below are run from inside `backend/`.

### Migration prerequisites

Add `SUPABASE_DB_URL` to `backend/.env`. This must be a Postgres connection
string, not the REST API URL. Example shape:

```dotenv
SUPABASE_DB_URL=postgres://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require
```

### Apply migrations

```bash
cd backend
./scripts/run-migrations.sh up
```

The helper script will:

- Load `backend/.env`
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

### Regenerate the schema snapshot

```bash
./scripts/run-migrations.sh up   # apply the new migration
./scripts/dump-schema.sh         # re-render sql/schema.sql from the live DB
git add sql/migrations/<new-file>.sql sql/schema.sql
```

### Docker startup behaviour

`docker compose up --build` runs:

1. `migrate` service using `ghcr.io/amacneil/dbmate`
2. Validates `SUPABASE_DB_URL` inside the container and runs `dbmate up`
3. `backend` service only after migrations complete successfully

### Troubleshooting Docker migrations

If you see:

```text
Error: unable to connect to database: dial tcp [::1]:5432: connect: connection refused
```

that usually means the migration container did not receive a usable
`SUPABASE_DB_URL`, so `dbmate` fell back to `localhost` inside Docker.

Check these exactly:

1. `backend/.env` contains `SUPABASE_DB_URL=postgres://...`
2. The hostname inside `SUPABASE_DB_URL` is not `localhost`, `127.0.0.1`, or `::1`
3. For hosted Supabase, use the project Postgres host like `db.<project-ref>.supabase.co`
4. For a database running on your machine, use `host.docker.internal` instead of `localhost`

## Admin Reset Scripts

Two destructive reset utilities are included for explicit operational use.
They are intentionally separate from `sql/migrations/` so they never run as
part of normal schema migration startup.

Run all scripts from inside `backend/`.

Before using any of these scripts:

- Confirm you are targeting the correct Supabase project
- Confirm `backend/.env` points at the intended environment
- Treat these commands as destructive and non-routine

### Truncate all application tables and delete all users

SQL source:

- [backend/sql/admin/202604160101_truncate_all_tables.sql](backend/sql/admin/202604160101_truncate_all_tables.sql)

Wrapper:

```bash
cd backend
chmod +x scripts/truncate-all-tables.sh
./scripts/truncate-all-tables.sh --yes
```

Behavior:

- Loads `backend/.env`
- Requires `SUPABASE_DB_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`
- Requires `curl` and `jq` on `PATH` for the user-deletion step
- Step 1 — executes the SQL file with `psql`, falling back to a disposable `postgres:16-alpine` container if `psql` is not installed; truncates `eval_sample_results`, `eval_runs`, `prompt_versions`, `documents`, `ingestion_jobs`, and `tenants`
- Step 2 — paginates `GET /auth/v1/admin/users` and issues `DELETE /auth/v1/admin/users/{id}` for every Supabase Auth user until none remain; aborts on the first non-2xx response

### Empty the Supabase Storage bucket

Storage deletion must go through the Supabase Storage API, not direct SQL.

#### CLI execution standard (recommended)

Run from inside `backend/`:

```bash
python -m app.cli.purge_supabase_bucket --yes
```

Compatible legacy invocation:

```bash
python scripts/purge-supabase-bucket.py --yes
```

Installable CLI entry point (after editable install):

```bash
ragfier-purge-bucket --yes
```

Optional bucket override:

```bash
python -m app.cli.purge_supabase_bucket --yes --bucket documents
```

#### Command matrix

| Command form | Status | Notes |
|---|---|---|
| `python -m app.cli.purge_supabase_bucket --yes` | Preferred | Canonical, package-native execution |
| `python scripts/purge-supabase-bucket.py --yes` | Supported | Backward-compatible wrapper |
| `ragfier-purge-bucket --yes` | Supported | Requires project install with entry points |

### Full environment reset

```bash
cd backend
chmod +x scripts/reset-environment.sh
./scripts/reset-environment.sh --yes
```

Behavior:

- Empties the configured Supabase Storage bucket first
- Truncates all application tables second
- Stops immediately if either step fails

Equivalent manual order:

1. `python3 -m app.cli.purge_supabase_bucket --yes`
2. `./scripts/truncate-all-tables.sh --yes`

## Testing

Run from inside `backend/`:

```bash
pytest tests/ -v
pytest tests/ --cov=app --cov-report=term-missing
deepeval test run tests/test_rag_evaluation.py --verbose
```

Tests use in-memory fakes for Supabase, OpenAI (sync + streaming), and the
reranker — no network, no real API keys, no Cohere/`sentence-transformers`
install required for the unit suite. The DeepEval suite is separate and
intended for Phase 3 quality gating. See [backend/tests/fakes.py](backend/tests/fakes.py).

Suite: **76 tests** — parser, chunker (including section-aware grouping
and cross-section isolation), contextualizer (disabled-by-default no-op,
prompt-cached Claude Haiku call, API-error fallback), embedder,
ingestion pipeline, API, RRF fusion (classic + OpenAI-style weighted),
reranker fallback, generator (sync + streaming), citation resolver,
prompt loader precedence, evaluation runner/API/custom metrics, hosted
platform auth, `/v1` knowledge bases/documents/connectors/query, SDK
coverage, and end-to-end `/query`, `/query/stream`, and `/prompts`
round-trip.

## Phase 3 Evaluation Workflow

### What is implemented

- Versioned golden dataset support via [backend/eval/datasets/golden_v1.0.0.json](backend/eval/datasets/golden_v1.0.0.json).
- Ragas-based scoring for faithfulness, answer relevancy, context precision, and context recall.
- Custom evaluation metrics for citation coverage, decline accuracy, and latency compliance.
- Threshold-based pass/fail aggregation with YAML config in [backend/eval/config/thresholds.yaml](backend/eval/config/thresholds.yaml).
- Persisted evaluation history in `eval_runs` and `eval_sample_results`, added by [backend/sql/migrations/202604160003_phase3_eval_pipeline.sql](backend/sql/migrations/202604160003_phase3_eval_pipeline.sql).
- Tenant-scoped evaluation APIs in [backend/app/api/eval.py](backend/app/api/eval.py).
- CLI entry points for running, generating, listing, and comparing evaluation runs.
- GitHub Actions workflow in [.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml).
- Unit and integration coverage in [backend/tests/test_eval_runner.py](backend/tests/test_eval_runner.py), [backend/tests/test_eval_api.py](backend/tests/test_eval_api.py), [backend/tests/test_custom_metrics.py](backend/tests/test_custom_metrics.py), and [backend/tests/test_rag_evaluation.py](backend/tests/test_rag_evaluation.py).

### Metrics and thresholds

Thresholds live in [backend/eval/config/thresholds.yaml](backend/eval/config/thresholds.yaml) and are overridable per-env; `blocking: true` metrics fail the CI gate, `blocking: false` metrics only warn.

| Metric | What it measures | Source | Threshold | Blocking |
|--------|------------------|--------|-----------|----------|
| Faithfulness | Share of answer claims entailed by retrieved context | Ragas | ≥ 0.85 | Yes |
| Answer Relevancy | How on-topic the answer is vs. the user's question | Ragas | ≥ 0.80 | Yes |
| Context Precision | Whether relevant chunks are ranked above irrelevant ones | Ragas | ≥ 0.75 | Yes |
| Context Recall | Whether retrieval surfaced all info needed for the reference | Ragas | ≥ 0.75 | No (warn) |
| Citation Coverage | % of factual sentences carrying `[SOURCE_N]` anchors | Custom — [backend/eval/metrics/citation_coverage.py](backend/eval/metrics/citation_coverage.py) | ≥ 0.90 | Yes |
| Decline Accuracy | Correct decline on unanswerable / correct answer on answerable | Custom — [backend/eval/metrics/decline_accuracy.py](backend/eval/metrics/decline_accuracy.py) | ≥ 0.80 | Yes |
| Latency Compliance | % of queries completing within the configured budget | Custom — [backend/eval/metrics/latency_compliance.py](backend/eval/metrics/latency_compliance.py) | ≥ 0.90 | No (warn) |

Aggregation additionally enforces `min_passing_rate` (default 0.80) — at least that fraction of samples must pass every blocking metric for the run to pass.

### Golden dataset shape

Golden datasets are versioned JSON under [backend/eval/datasets/](backend/eval/datasets/) with a [CHANGELOG.md](backend/eval/datasets/CHANGELOG.md). Samples span six categories — `exact_match`, `conceptual`, `multi_context`, `unanswerable`, `reasoning`, `adversarial`. The spec targets ≥ 50 manually-reviewed samples; the checked-in `golden_v1.0.0.json` ships 14 seed samples. Adversarial samples (`category: "adversarial"`) are treated identically to unanswerable ones and are excluded from faithfulness, context precision, and context recall scoring.

### Local commands

Run from inside `backend/`:

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

- [.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml) triggers on PRs touching `backend/app/pipeline/`, `backend/prompts/`, `backend/sql/`, `backend/eval/`, or `backend/tests/test_rag_evaluation.py`.
- The workflow sets `defaults.run.working-directory: backend` so all `run:` steps execute inside `backend/` without explicit `cd`.
- The workflow runs Phase 3 unit tests first, then `deepeval test run tests/test_rag_evaluation.py`.
- Evaluation reports are uploaded as artifacts from `backend/eval/reports/`.

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
  "overlap_tokens": 100,
  "contextualized": true
}
```

Missing values are stored as `null` — never dropped. The resolver preserves
all of this on every `Citation` returned from `/query`. The optional
`contextualized` flag is set to `true` when the Anthropic contextualizer
ran against the chunk; `ChunkMetadata` keeps `extra="allow"` so the flag
round-trips without a schema migration.

## Multi-Tenancy

- Ingestion runs with `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS).
- Client-facing reads use `anon`/`authenticated` keys; RLS policies in
  [backend/sql/migrations/](backend/sql/migrations/)
  filter on `tenant_id = auth.jwt() -> 'app_metadata' ->> 'organization_id'`.
- `match_documents` and `match_documents_hybrid` both accept
  `filter_tenant_id` and `filter_integration_id` for explicit server-side
  scoping — the query pipeline always passes both, so the LLM never sees
  cross-tenant or cross-integration chunks.
- `prompt_versions` supports tenant-specific overrides (`tenant_id = <uuid>`)
  alongside global prompts (`tenant_id IS NULL`); the loader prefers the
  tenant row when both exist.
- Hosted `/v1` routes do not accept caller-controlled tenant identifiers.
  Tenant scope is derived from the API key record, which also ties every
  public request to an `integration_id` and `api_key_id`.
- Every tenant is automatically provisioned with a **default global
  integration** at signup. Requests that omit `integration_id` (ingest,
  query, stream) resolve to this default automatically.

## Hosted Platform

Phase 4 introduces the first hosted control-plane and public API layer.

### Data model additions

- `integrations`: named app installations or environments under a tenant; one default global integration is auto-provisioned per tenant
- `api_keys`: per-integration keys with hashed secrets, scopes, expiry, status, and last-used timestamps
- `knowledge_bases`: tenant-owned logical collections (legacy KB-centric path, deprecated in favour of integration-scoped endpoints)
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
back to `backend/prompts/<name>.yaml`. The default prompt ships as
[backend/prompts/rag_generation_v1.yaml](backend/prompts/rag_generation_v1.yaml).

YAML prompts can reference centralised settings using `${setting_name}`. Example:

```yaml
model: ${generation_model}
temperature: ${generation_temperature}
max_tokens: ${generation_max_tokens}
```

Those values are resolved through the same settings chain above, so prompt
files can stay declarative without duplicating non-sensitive defaults.

The default prompt ([backend/prompts/rag_generation_v1.yaml](backend/prompts/rag_generation_v1.yaml))
hard-constrains the LLM to the provided context and requires `[SOURCE_N]`
anchors on every factual claim, but also enables **grounded reasoning** so
the model can answer realistic questions that require light inference
over the cited evidence:

- **Temporal reasoning** — treat an entry with "Jan 2024 – Present" as
  the current role/company when a user asks "where does X work now?"
- **Ranking / superlatives** — compare enumerated items in the retrieved
  chunks (e.g. "best project") and justify the choice from explicit
  attributes in the evidence.
- **Aggregation** — count or compare items that are all present in
  context (e.g. "how many projects has X shipped?").
- **Synonym resolution** — align query phrasing with context phrasing
  ("current employer" ≈ "present role").

When the retrieved context genuinely does not support an answer — even
with the above reasoning — the prompt mandates the canonical decline
message. This is the second layer of hallucination defence on top of the
relevance-threshold short-circuit in the retrieval pipeline.

## Phase 1 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Working ingestion pipeline | Done |
| 2 | Supabase pgvector schema + RLS + HNSW | Done |
| 3 | Chunk + embedding storage with metadata | Done |
| 4 | Retrieval via `match_documents` | Done |
| 5 | REST API (`/ingest`, `/status`, `/query`, `/health`) | Done |
| 6 | Multi-tenant isolation | Done (RLS + `tenant_id` on every row) |
| 7 | Test suite | Done |
| 8 | Docker-ready deployment | Done |

## Phase 2 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Full-text search column + GIN index | Done ([backend/sql/migrations/202604160002_phase2_hybrid_query.sql](backend/sql/migrations/202604160002_phase2_hybrid_query.sql)) |
| 2 | `match_documents_hybrid` RRF function | Done |
| 3 | Cross-encoder reranking (Cohere + local fallback) | Done |
| 4 | Citation-enforced generation (`[SOURCE_N]` anchors resolved to metadata) | Done |
| 5 | Hallucination guardrails (relevance threshold + prompt-based decline) | Done |
| 6 | Updated `/query` endpoint (embed → hybrid → rerank → generate → cite) | Done |
| 7 | Streaming `/query/stream` (SSE with up-front `sources` event) | Done |
| 8 | Prompt management (`/prompts` + YAML fallback) | Done |
| 9 | Per-step latency tracking in response metadata | Done |
| 10 | Phase 2 test suite | Done |

## Retrieval Quality Enhancements — Status

Targeted upgrades that close the gap on realistic user questions (superlatives, "current" queries, enumeration). Delivered alongside Phase 2.

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Section-aware chunk grouping (keeps short enumerated sections in one chunk) | Done ([backend/app/pipeline/chunker.py](backend/app/pipeline/chunker.py), [backend/tests/test_chunker.py](backend/tests/test_chunker.py)) |
| 2 | OpenAI File-Search-style weighted RRF in SQL + Python client with backward-compat fallback | Done ([backend/sql/migrations/202604180005_weighted_hybrid_rrf.sql](backend/sql/migrations/202604180005_weighted_hybrid_rrf.sql), [backend/app/pipeline/fusion.py](backend/app/pipeline/fusion.py), [backend/app/pipeline/retriever_sparse.py](backend/app/pipeline/retriever_sparse.py)) |
| 3 | Anthropic contextual retrieval with prompt caching (`cache_control: ephemeral`) | Done ([backend/app/pipeline/contextualizer.py](backend/app/pipeline/contextualizer.py), [backend/tests/test_contextualizer.py](backend/tests/test_contextualizer.py)) |
| 4 | Contextualizer wiring in ingestion orchestrator with `contextualizing` job status | Done ([backend/app/pipeline/orchestrator.py](backend/app/pipeline/orchestrator.py)) |
| 5 | Softened generation prompt allowing grounded reasoning (temporal / ranking / aggregation / synonym) | Done ([backend/prompts/rag_generation_v1.yaml](backend/prompts/rag_generation_v1.yaml)) |
| 6 | Retrieval depth tuning: `rerank_top_k` default 5 → 8, API `match_count` default 5 → 8 | Done ([backend/app/config.py](backend/app/config.py), [backend/app/models/schemas.py](backend/app/models/schemas.py)) |
| 7 | Graceful fallback to unweighted RRF when the weighted RPC is not yet migrated | Done ([backend/app/pipeline/retriever_sparse.py](backend/app/pipeline/retriever_sparse.py)) |

## Phase 3 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Golden dataset (v1.0.0) with versioned JSON + CHANGELOG | Done — seed of 14 samples; expanding toward the ≥50-sample target |
| 2 | Synthetic test generation pipeline | Done ([backend/eval/generate.py](backend/eval/generate.py)) |
| 3 | Ragas evaluation pipeline | Done ([backend/eval/ragas_runner.py](backend/eval/ragas_runner.py)) |
| 4 | Custom metrics (Citation Coverage, Decline Accuracy, Latency Compliance) | Done ([backend/eval/metrics/](backend/eval/metrics/)) |
| 5 | DeepEval pytest suite with pass/fail thresholds | Done ([backend/tests/test_rag_evaluation.py](backend/tests/test_rag_evaluation.py)) |
| 6 | GitHub Actions CI quality gate | Done ([.github/workflows/rag-evaluation.yml](.github/workflows/rag-evaluation.yml)) |
| 7 | Evaluation storage schema with RLS | Done ([backend/sql/migrations/202604160003_phase3_eval_pipeline.sql](backend/sql/migrations/202604160003_phase3_eval_pipeline.sql)) |
| 8 | `/eval/run`, `/eval/runs`, `/eval/runs/{id}/samples` APIs | Done ([backend/app/api/eval.py](backend/app/api/eval.py)) |
| 9 | CLI tools: `eval.run`, `eval.generate`, `eval.history`, `eval.compare` | Done |
| 10 | Historical score tracking + run comparison | Done |
| 11 | Threshold configuration decoupled from code | Done ([backend/eval/config/thresholds.yaml](backend/eval/config/thresholds.yaml)) |
| 12 | Phase 3 test coverage | Done |

## Phase 4 Deliverables — Status

| # | Deliverable | Status |
|---|-------------|--------|
| 1 | Hosted `/v1` API with API-key auth | Done |
| 2 | JWT dashboard platform endpoints for integrations and API keys | Done |
| 3 | Default global integration auto-provisioned on tenant signup | Done |
| 4 | Integration-scoped document upload/list endpoints (`/v1/integrations/{id}/documents`) | Done |
| 5 | Integration-scoped query + stream endpoints (`/v1/integrations/{id}/query[/stream]`) | Done |
| 6 | Flat API-key query endpoints (`/v1/query/integration[/stream]`) | Done |
| 7 | Integration fallback resolution in `/ingest`, `/query`, `/query/stream` | Done |
| 8 | Request/audit logging tables and API exposure | Done |
| 9 | Connector source + sync job schema and APIs (deprecated, record layer only) | Done |
| 10 | Python server SDK | Done |
| 11 | Secure API key hashing + encrypted connector config | Done |
| 12 | Repository split into `backend/` + `frontend/` workspaces | Done |
| 13 | Multi-service `docker-compose.yml` with frontend stub | Done |
| 14 | Full dashboard UI | Not yet implemented |
| 15 | Durable connector execution workers | Not yet implemented |
| 16 | Browser/widget delivery + PDF overlay UX | Not yet implemented |
