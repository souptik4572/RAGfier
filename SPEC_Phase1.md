# SPEC.md — Phase 1: Technical Foundation for Domain-Specific RAG Ingestion

---

## 1. Executive Summary

Phase 1 establishes the ingestion backbone of a production-grade, multi-tenant RAG system. The objective is to convert unstructured domain documents (PDFs, Markdown) into structured, searchable, and citation-aware vector representations stored in Supabase pgvector.

This phase is the foundation upon which all subsequent phases (hybrid retrieval, reranking, evaluation, SDK delivery) will be built. Every architectural decision made here — from parser selection to metadata schema — is optimized for eventual multi-tenant SaaS deployment.

### Phase 1 Scope

- Layout-aware document parsing with spatial metadata extraction
- Semantically meaningful chunking with context retention
- High-quality embedding generation
- Multi-tenant vector storage with Row-Level Security (RLS)
- Basic retrieval API for validation
- Citation-ready metadata pipeline

### Out of Scope (Deferred to Later Phases)

- Hybrid search (BM25 + vector) → Phase 2
- Cross-encoder reranking → Phase 2
- Citation enforcement in LLM output → Phase 2
- Automated evaluation pipeline (Ragas) → Phase 3
- AI SDK / Chat widget / Frontend delivery → Phase 4

---

## 2. Architectural Goals

1. **Preserve Document Structure**: Maintain headers, tables, sections, and hierarchical relationships during parsing.
2. **Enforce Fine-Grained Citations**: Capture page numbers and bounding box coordinates at parse time so every chunk is traceable to its source location.
3. **Enable Multi-Tenant Isolation**: Use Supabase RLS with `tenant_id` / `organization_id` to ensure data isolation from day one.
4. **Ensure SaaS Scalability**: Design the schema and pipeline to support hundreds of tenants and thousands of documents without architectural changes.
5. **Maintain High Retrieval Precision**: Optimize chunking strategy and embedding quality to maximize signal-to-noise ratio during retrieval.
6. **Build for Extensibility**: Structure the pipeline so hybrid search, reranking, and evaluation can be layered on without refactoring core components.

---

## 3. Tech Stack

### 3.1 Core Backend

| Component        | Technology              | Rationale                                                                 |
|------------------|-------------------------|---------------------------------------------------------------------------|
| Language         | Python 3.10+            | Ecosystem support for ML/AI libraries                                     |
| API Framework    | FastAPI                 | Async-native, automatic OpenAPI docs, high performance                    |
| Orchestration    | LangChain / LangGraph   | Pipeline orchestration, chain composition, future agent support           |

### 3.2 Parsing Layer

| Component        | Technology              | Rationale                                                                 |
|------------------|-------------------------|---------------------------------------------------------------------------|
| PDF Parser       | LlamaParse              | Layout-aware extraction; identifies headers, tables, multi-column layouts |
| Markdown Parser  | LlamaParse / Python-Markdown | Fallback for non-PDF sources                                        |

### 3.3 Embedding Layer

| Component        | Technology                        | Rationale                                                        |
|------------------|-----------------------------------|------------------------------------------------------------------|
| Embedding Model  | OpenAI `text-embedding-3-small`   | 1536 dimensions, cost-effective, strong semantic representation  |
| Dimensionality   | 1536                              | Good balance of precision vs. storage/compute cost               |

### 3.4 Storage Layer

| Component          | Technology                     | Rationale                                                          |
|--------------------|--------------------------------|--------------------------------------------------------------------|
| Vector Database    | Supabase PostgreSQL + pgvector | Integrated relational + vector storage; native RLS for multi-tenancy |
| Document Storage   | Supabase Storage               | Raw file hosting with signed URLs for processing                   |
| Auth & Security    | Supabase Auth + JWT            | Built-in JWT-based auth with `app_metadata` for tenant routing     |

### 3.5 Infrastructure & Tooling

| Component          | Technology              | Rationale                                                          |
|--------------------|-------------------------|--------------------------------------------------------------------|
| Background Jobs    | Celery (optional)       | Async batch ingestion for large document sets                      |
| Queue / Cache      | Redis (optional)        | Job queue for Celery; caching for repeated queries                 |
| Containerization   | Docker                  | Reproducible environments; future self-hosted deployment           |
| Environment Config | python-dotenv / Pydantic Settings | Secure management of API keys and config                  |

### 3.6 Development Dependencies

fastapi>=0.104.0
uvicorn[standard]>=0.24.0
supabase>=2.0.0
llama-parse>=0.4.0
langchain>=0.1.0
langchain-openai>=0.0.5
openai>=1.12.0
python-dotenv>=1.0.0
pydantic>=2.5.0
httpx>=0.25.0
python-multipart>=0.0.6

---

## 4. System Architecture

### 4.1 High-Level Pipeline Flow

┌──────────────┐
│  User Upload │
│  (PDF / MD)  │
└──────┬───────┘
│
▼
┌──────────────────┐
│ Supabase Storage  │  ← Raw file stored; signed URL generated
│ (Raw Documents)   │
└──────┬───────────┘
│
▼
┌──────────────────┐
│   LlamaParse      │  ← Layout-aware extraction
│ (Parsing Engine)  │     Outputs: text, headers, tables, bbox metadata
└──────┬───────────┘
│
▼
┌──────────────────┐
│  Chunking Engine  │  ← Recursive character splitting
│                   │     600-800 tokens, 100 token overlap
│                   │     Context injection (title, section heading)
└──────┬───────────┘
│
▼
┌──────────────────┐
│ Embedding Engine  │  ← OpenAI text-embedding-3-small
│ (Batch Processing)│     1536-dimensional vectors
└──────┬───────────┘
│
▼
┌──────────────────┐
│  Supabase pgvector│  ← Multi-tenant upsert with RLS
│  (Vector DB)      │     HNSW indexed for cosine similarity
└──────────────────┘

### 4.2 Component Interaction Diagram

┌─────────────────────────────────────────────────────────┐
│                      FastAPI Server                      │
│                                                         │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐            │
│  │ /ingest  │   │ /status  │   │  /query  │            │
│  └────┬────┘   └────┬─────┘   └────┬─────┘            │
│       │              │              │                   │
│       ▼              ▼              ▼                   │
│  ┌─────────────────────────────────────────┐           │
│  │        Pipeline Orchestrator             │           │
│  │        (LangChain / LangGraph)           │           │
│  └─────────────────────────────────────────┘           │
│       │              │              │                   │
│       ▼              ▼              ▼                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐            │
│  │ Parser   │  │ Chunker  │  │ Embedder  │            │
│  │ Module   │  │ Module   │  │ Module    │            │
│  └──────────┘  └──────────┘  └───────────┘            │
└─────────────────────┬───────────────────────────────────┘
│
▼
┌────────────────────────┐
│       Supabase         │
│  ┌──────────────────┐  │
│  │  Storage (Files) │  │
│  ├──────────────────┤  │
│  │  PostgreSQL +    │  │
│  │  pgvector (Data) │  │
│  ├──────────────────┤  │
│  │  Auth (JWT/RLS)  │  │
│  └──────────────────┘  │
└────────────────────────┘

---

## 5. Database Schema

### 5.1 Core Schema (PostgreSQL + pgvector)

```sql
-- =============================================================
-- Phase 1: Domain-Specific RAG Ingestion — Database Schema
-- =============================================================

-- Enable the pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================
-- Table: tenants
-- Purpose: Registry of all tenants (organizations) in the system
-- =============================================================
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,          -- URL-friendly identifier
  plan TEXT DEFAULT 'free',            -- Subscription tier
  settings JSONB DEFAULT '{}',         -- Tenant-specific config
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Table: ingestion_jobs
-- Purpose: Track the status and progress of each document ingestion
-- =============================================================
CREATE TABLE ingestion_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,             -- Path in Supabase Storage
  status TEXT NOT NULL DEFAULT 'pending',
    -- Valid statuses: pending | parsing | chunking | embedding | completed | failed
  total_chunks INTEGER DEFAULT 0,
  processed_chunks INTEGER DEFAULT 0,
  error_message TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Table: documents
-- Purpose: Store parsed, chunked, and embedded document fragments
-- =============================================================
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  job_id UUID REFERENCES ingestion_jobs(id) ON DELETE SET NULL,
  content TEXT NOT NULL,               -- The chunk text
  embedding VECTOR(1536),             -- OpenAI text-embedding-3-small output
  metadata JSONB NOT NULL DEFAULT '{}',
    -- Expected metadata structure:
    -- {
    --   "source": "contract.pdf",
    --   "document_id": "uuid-of-parent-file",
    --   "page_number": 5,
    --   "bounding_boxes": [[x0, y0, x1, y1], ...],
    --   "section_heading": "Section 3.2 — Liability",
    --   "document_title": "Master Services Agreement",
    --   "chunk_index": 12,
    --   "total_chunks": 45,
    --   "parser": "llamaparse",
    --   "chunk_strategy": "recursive_character",
    --   "chunk_size_tokens": 700,
    --   "overlap_tokens": 100
    -- }
  created_at TIMESTAMPTZ DEFAULT now()
);

-- =============================================================
-- Indexes
-- =============================================================

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX idx_documents_embedding
  ON documents
  USING hnsw (embedding vector_cosine_ops);

-- B-tree index for tenant-scoped queries
CREATE INDEX idx_documents_tenant_id
  ON documents (tenant_id);

-- B-tree index for job-based lookups
CREATE INDEX idx_documents_job_id
  ON documents (job_id);

-- GIN index for JSONB metadata queries (e.g., filter by source file)
CREATE INDEX idx_documents_metadata
  ON documents
  USING gin (metadata);

-- B-tree index for ingestion job status tracking
CREATE INDEX idx_ingestion_jobs_tenant_status
  ON ingestion_jobs (tenant_id, status);

-- =============================================================
-- Row-Level Security (RLS)
-- =============================================================

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY;

-- Policy: Authenticated users can only SELECT documents belonging to their org
CREATE POLICY "tenant_isolation_select" ON documents
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

-- Policy: Service role can INSERT documents (used by ingestion pipeline)
CREATE POLICY "service_role_insert" ON documents
  FOR INSERT
  WITH CHECK (true);
  -- Note: Ingestion runs with service_role key; RLS is bypassed.
  -- This policy exists for documentation clarity.

-- Policy: Authenticated users can only view their own ingestion jobs
CREATE POLICY "tenant_isolation_jobs" ON ingestion_jobs
  FOR SELECT
  USING (
    tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );

-- =============================================================
-- Functions
-- =============================================================

-- Function: match_documents
-- Purpose: Retrieve the top-k most similar document chunks for a query
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding VECTOR(1536),
  match_count INT DEFAULT 5,
  filter_tenant_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.content,
    d.metadata,
    1 - (d.embedding <=> query_embedding) AS similarity
  FROM documents d
  WHERE
    (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

### 5.2 Metadata Schema Reference

Every chunk stored in the `documents` table must include the following metadata fields:

| Field               | Type          | Required | Description                                              |
|---------------------|---------------|----------|----------------------------------------------------------|
| `source`            | string        | Yes      | Original filename (e.g., `"contract.pdf"`)               |
| `document_id`       | UUID          | Yes      | Unique ID of the parent document                         |
| `page_number`       | integer       | Yes      | Page number where the chunk originates                   |
| `bounding_boxes`    | array[array]  | Yes      | List of `[x0, y0, x1, y1]` coordinates for the text     |
| `section_heading`   | string        | No       | Nearest section heading above the chunk                  |
| `document_title`    | string        | No       | Title of the document (extracted or provided)            |
| `chunk_index`       | integer       | Yes      | Sequential index of this chunk within the document       |
| `total_chunks`      | integer       | Yes      | Total number of chunks produced from this document       |
| `parser`            | string        | Yes      | Parser used (e.g., `"llamaparse"`)                       |
| `chunk_strategy`    | string        | Yes      | Strategy used (e.g., `"recursive_character"`)            |
| `chunk_size_tokens` | integer       | Yes      | Actual token count of this chunk                         |
| `overlap_tokens`    | integer       | Yes      | Overlap tokens used                                      |

---

## 6. Ingestion Pipeline — Detailed Specification

### 6.1 Step 1: Document Upload

**Endpoint**: `POST /ingest`

**Process**:

1. Accept file upload (PDF or Markdown) via multipart form data.
2. Validate file type and size (configurable max, default 50MB).
3. Upload raw file to Supabase Storage bucket (`documents/{tenant_id}/{filename}`).
4. Generate a signed URL for downstream processing (expiry: 1 hour).
5. Create an `ingestion_jobs` record with status `pending`.
6. Trigger the ingestion pipeline asynchronously.
7. Return the `job_id` to the client for status polling.

**Request**:
```json
POST /ingest
Content-Type: multipart/form-data
Authorization: Bearer <jwt_token>

{
  "file": <binary>,
  "document_title": "Master Services Agreement"  // optional override
}
```

**Response**:
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Ingestion pipeline started"
}
```

### 6.2 Step 2: Layout-Aware Parsing

**Tool**: LlamaParse

**Process**:

1. Update job status to `parsing`.
2. Fetch the file from Supabase Storage using the signed URL.
3. Pass the file to LlamaParse with layout-aware mode enabled.
4. Extract structured output containing:
   - Full text content
   - Header hierarchy (H1, H2, H3, etc.)
   - Table structures (preserved as Markdown tables)
   - Section boundaries
5. For each text block, capture spatial metadata:
   - `page_number`: The page where the block appears.
   - `bounding_boxes`: The `[x0, y0, x1, y1]` coordinates of the block on the page.
6. If parsing fails, update job status to `failed` with error message.

**LlamaParse Configuration**:
```python
from llama_parse import LlamaParse

parser = LlamaParse(
    api_key=LLAMA_CLOUD_API_KEY,
    result_type="markdown",           # Structured Markdown output
    parsing_instruction=(
        "Extract all text preserving section hierarchy. "
        "Preserve table structures as Markdown tables. "
        "Identify and tag all headers with their level."
    ),
    verbose=True,
)

documents = parser.load_data(file_path)
```

**Output Structure** (per parsed block):
```json
{
  "text": "The liability cap shall not exceed $1,000,000...",
  "page_number": 5,
  "bounding_boxes": [[72, 340, 540, 380]],
  "section_heading": "Section 3.2 — Limitation of Liability",
  "element_type": "paragraph"
}
```

### 6.3 Step 3: Chunking Strategy

**Method**: Recursive Character Splitting with Context Injection

**Parameters**:

| Parameter       | Value      | Rationale                                                       |
|-----------------|------------|-----------------------------------------------------------------|
| Chunk Size      | 600–800 tokens | Fits within LLM context; preserves semantic coherence       |
| Overlap         | 100 tokens | Prevents loss of context at chunk boundaries                    |
| Separators      | `["\n\n", "\n", ". ", " "]` | Splits on semantic boundaries first          |

**Process**:

1. Update job status to `chunking`.
2. For each parsed block, apply recursive character splitting.
3. Respect semantic boundaries: prefer splitting at paragraph breaks, then sentence breaks.
4. For each chunk, inject situated context:
   - Prepend the document title (if available).
   - Prepend the nearest section heading.
   - This helps the embedding model understand the chunk's place in the document.
5. Assign sequential `chunk_index` values.
6. Calculate `total_chunks` for the document.
7. Preserve the spatial metadata (page number, bounding boxes) from the parsing step.

**Implementation**:
```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=700,           # Target: 600-800 token range
    chunk_overlap=100,
    length_function=token_counter,  # Use tiktoken for accurate token counting
    separators=["\n\n", "\n", ". ", " "],
)

chunks = splitter.split_documents(parsed_documents)
```

**Context Injection Example**:

[Document: Master Services Agreement]
[Section: 3.2 — Limitation of Liability]
The liability cap shall not exceed $1,000,000 in aggregate for all
claims arising under this agreement. This limitation applies to both
direct and indirect damages...

### 6.4 Step 4: Embedding Generation

**Model**: OpenAI `text-embedding-3-small` (1536 dimensions)

**Process**:

1. Update job status to `embedding`.
2. Collect all chunks for the document.
3. Batch chunks into groups (max 2048 chunks per API call, per OpenAI limits).
4. Send batches to the OpenAI Embeddings API.
5. Handle rate limiting with exponential backoff.
6. Map each embedding vector back to its corresponding chunk.

**Implementation**:
```python
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_embeddings(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Generate embeddings in batches with rate limiting."""
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)
    return all_embeddings
```

**Cost Estimation** (as of 2025):
- `text-embedding-3-small`: ~$0.02 per 1M tokens
- A 100-page PDF ≈ 50,000 tokens ≈ ~$0.001 per document
- At scale: 10,000 documents ≈ ~$10.00

### 6.5 Step 5: Multi-Tenant Upsert

**Process**:

1. For each chunk + embedding pair, construct a record containing:
   - `tenant_id` (from authenticated user's JWT)
   - `job_id` (from the ingestion job)
   - `content` (the chunk text)
   - `embedding` (the 1536-dim vector)
   - `metadata` (full metadata object as defined in Section 5.2)
2. Batch upsert records into the `documents` table via Supabase client.
3. Update `ingestion_jobs.processed_chunks` as records are inserted.
4. On completion, update job status to `completed` and set `total_chunks`.

**Implementation**:
```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def upsert_chunks(tenant_id: str, job_id: str, chunks: list[dict]):
    """Batch upsert chunks with embeddings into Supabase."""
    records = []
    for chunk in chunks:
        records.append({
            "tenant_id": tenant_id,
            "job_id": job_id,
            "content": chunk["content"],
            "embedding": chunk["embedding"],
            "metadata": chunk["metadata"],
        })

    # Batch insert (Supabase supports bulk inserts)
    response = supabase.table("documents").insert(records).execute()
    return response
```

---

## 7. Retrieval Contract (Phase 1 — Basic Vector Search)

### 7.1 Function: `match_documents`

Phase 1 implements basic cosine similarity retrieval. Hybrid search (BM25 + vector) and reranking are deferred to Phase 2.

**Input**:

| Parameter          | Type          | Required | Default | Description                       |
|--------------------|---------------|----------|---------|-----------------------------------|
| `query_embedding`  | vector(1536)  | Yes      | —       | Embedding of the user's query     |
| `match_count`      | integer       | No       | 5       | Number of results to return       |
| `filter_tenant_id` | UUID          | No       | NULL    | Tenant scope (enforced via RLS)   |

**Output** (per result):

| Field        | Type   | Description                                    |
|--------------|--------|------------------------------------------------|
| `id`         | UUID   | Chunk ID                                       |
| `content`    | text   | The chunk text                                 |
| `metadata`   | JSONB  | Full metadata (source, page, bbox, etc.)       |
| `similarity` | float  | Cosine similarity score (0 to 1)               |

### 7.2 Query Flow

User Query (text)
│
▼
Embed query → OpenAI text-embedding-3-small
│
▼
Call match_documents(query_embedding, match_count=5)
│
▼
Return top-k chunks with content + metadata
│
▼
(Phase 2: Pass to LLM with citation enforcement)

---

## 8. API Design (Phase 1)

### 8.1 Endpoints

#### `POST /ingest`

Upload a document and trigger the ingestion pipeline.

**Headers**:
- `Authorization: Bearer <jwt_token>` (tenant identity)

**Body**: multipart/form-data with `file` field

**Response** (`202 Accepted`):
```json
{
  "job_id": "uuid",
  "status": "pending",
  "message": "Ingestion pipeline started"
}
```

---

#### `GET /status/{job_id}`

Poll the progress of an ingestion job.

**Headers**:
- `Authorization: Bearer <jwt_token>`

**Response** (`200 OK`):
```json
{
  "job_id": "uuid",
  "status": "embedding",
  "file_name": "contract.pdf",
  "total_chunks": 45,
  "processed_chunks": 32,
  "created_at": "2025-04-13T10:00:00Z",
  "updated_at": "2025-04-13T10:02:15Z"
}
```

**Status Values**: `pending` → `parsing` → `chunking` → `embedding` → `completed` | `failed`

---

#### `POST /query`

Accept a natural language query and return relevant chunks.

**Headers**:
- `Authorization: Bearer <jwt_token>`

**Body**:
```json
{
  "query": "What is the liability cap in the MSA?",
  "match_count": 5
}
```

**Response** (`200 OK`):
```json
{
  "query": "What is the liability cap in the MSA?",
  "results": [
    {
      "id": "uuid",
      "content": "The liability cap shall not exceed...",
      "metadata": {
        "source": "contract.pdf",
        "page_number": 5,
        "bounding_boxes": [[72, 340, 540, 380]],
        "section_heading": "Section 3.2 — Limitation of Liability",
        "document_title": "Master Services Agreement"
      },
      "similarity": 0.92
    }
  ]
}
```

---

#### `GET /health`

Health check endpoint.

**Response** (`200 OK`):
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "supabase": "connected",
  "openai": "connected"
}
```

---

## 9. Security Model

### 9.1 Key Separation

| Key Type             | Used By                | Permissions                              |
|----------------------|------------------------|------------------------------------------|
| `service_role` key   | Ingestion pipeline     | Full DB access; bypasses RLS             |
| `anon` / `authenticated` key | Client-side queries | Read-only; scoped by RLS policies     |

### 9.2 Tenant Isolation Flow

Client Request (with JWT)
│
▼
Supabase Auth verifies JWT
│
▼
Extract organization_id from app_metadata
│
▼
RLS policy filters: tenant_id = organization_id
│
▼
Only tenant's own documents are returned

### 9.3 Security Checklist

- [ ] `service_role` key stored in server-side environment variables only
- [ ] `anon` key used only in client-side requests
- [ ] RLS enabled on `documents` and `ingestion_jobs` tables
- [ ] JWT `app_metadata.organization_id` set during user registration
- [ ] File uploads scoped to tenant directory: `documents/{tenant_id}/`
- [ ] Signed URLs expire after 1 hour
- [ ] Input validation on file type (PDF, MD only) and size (max 50MB)

---

## 10. Project Structure

rag-ingestion/
├── app/
│   ├── init.py
│   ├── main.py                    # FastAPI app initialization
│   ├── config.py                  # Pydantic Settings (env vars)
│   ├── api/
│   │   ├── init.py
│   │   ├── ingest.py              # POST /ingest endpoint
│   │   ├── status.py              # GET /status/{job_id} endpoint
│   │   ├── query.py               # POST /query endpoint
│   │   └── health.py              # GET /health endpoint
│   ├── pipeline/
│   │   ├── init.py
│   │   ├── orchestrator.py        # Main pipeline coordinator
│   │   ├── parser.py              # LlamaParse integration
│   │   ├── chunker.py             # Recursive character splitter
│   │   ├── embedder.py            # OpenAI embedding generation
│   │   └── upserter.py            # Supabase batch upsert
│   ├── models/
│   │   ├── init.py
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── database.py            # Supabase client initialization
│   └── utils/
│       ├── init.py
│       ├── token_counter.py       # tiktoken-based token counting
│       └── logger.py              # Structured logging setup
├── sql/
│   └── schema.sql                 # Full database schema (Section 5.1)
├── tests/
│   ├── init.py
│   ├── test_parser.py
│   ├── test_chunker.py
│   ├── test_embedder.py
│   ├── test_pipeline.py
│   └── test_api.py
├── .env.example                   # Template for environment variables
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md

---

## 11. Environment Variables

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...       # Server-side only; never expose
SUPABASE_ANON_KEY=eyJ...               # Client-side safe

# OpenAI
OPENAI_API_KEY=sk-...

# LlamaParse
LLAMA_CLOUD_API_KEY=llx-...

# Application
APP_ENV=development                     # development | staging | production
APP_VERSION=0.1.0
MAX_FILE_SIZE_MB=50
ALLOWED_FILE_TYPES=pdf,md

# Optional: Celery + Redis
REDIS_URL=redis://localhost:6379/0
```

---

## 12. Engineering Considerations

### 12.1 Performance

- **Batch Embeddings**: Process chunks in batches of 100 to minimize API round-trips.
- **HNSW Indexing**: Use `vector_cosine_ops` for optimized ANN search. HNSW provides sub-linear query time.
- **Connection Pooling**: Use Supabase's built-in connection pooler (PgBouncer) for high-concurrency workloads.
- **Async Processing**: FastAPI's async endpoints ensure the API remains responsive during pipeline execution.

### 12.2 Reliability

- **Retry Logic**: Implement exponential backoff for OpenAI API calls and Supabase upserts (max 3 retries).
- **Idempotent Processing**: Use `job_id` to prevent duplicate chunk insertion on retries.
- **Graceful Failure**: If any pipeline step fails, update `ingestion_jobs.status` to `failed` with a descriptive `error_message`.
- **Atomic Status Updates**: Use database transactions to ensure job status and chunk counts stay consistent.

### 12.3 Observability

- **Structured Logging**: Log each pipeline step with `job_id`, `tenant_id`, timestamp, and duration.
- **Metrics to Track**:
  - Ingestion latency (total and per-step)
  - Chunks per document
  - Embedding API latency
  - Failed ingestion rate
  - Storage utilization per tenant
- **Error Tracking**: Log full stack traces for failed jobs; include document metadata for debugging.

### 12.4 Scalability Notes

- **Tenant Growth**: The Pool pattern (shared index + RLS) scales to hundreds of tenants. Monitor query latency as the index grows.
- **Document Volume**: For >100k chunks, consider partitioning the `documents` table by `tenant_id`.
- **Embedding Costs**: At 10k+ documents/month, evaluate switching to open-source embedding models (e.g., `all-MiniLM-L6-v2`) to reduce cost.

---

## 13. Deliverables (Phase 1 Completion Criteria)

| #  | Deliverable                                      | Acceptance Criteria                                                |
|----|--------------------------------------------------|--------------------------------------------------------------------|
| 1  | Working ingestion pipeline                       | PDF upload → parse → chunk → embed → store in Supabase             |
| 2  | Supabase pgvector database setup                 | Schema deployed; RLS policies active; HNSW index created           |
| 3  | Chunk + embedding storage with metadata          | Every chunk has content, embedding, page number, bounding boxes    |
| 4  | Retrieval-ready dataset with citations            | `match_documents` returns ranked chunks with full metadata         |
| 5  | RESTful API (3 endpoints)                        | `/ingest`, `/status/{job_id}`, `/query` all functional             |
| 6  | Multi-tenant isolation                           | Tenant A cannot access Tenant B's documents via API                |
| 7  | Basic test suite                                 | Unit tests for parser, chunker, embedder; integration test for API |
| 8  | Docker-ready deployment                          | `docker-compose up` brings up the full stack locally               |

---

## 14. Phase 2 Preview (Next Steps)

Phase 2 will build on this foundation by introducing:

1. **Hybrid Search**: Combine BM25 (sparse/keyword) retrieval with vector (dense/semantic) retrieval using Reciprocal Rank Fusion (RRF).
2. **Cross-Encoder Reranking**: Use a cross-encoder model to rescore candidate chunks for higher precision before passing to the LLM.
3. **Citation Enforcement in LLM Output**: Instruct the LLM to generate responses with citation anchors that map back to the metadata captured in Phase 1.
4. **Hallucination Guardrails**: If retrieved context does not contain the answer, the system will explicitly decline rather than hallucinate.

---

## 15. Key Insight

> A production RAG system is only as good as its ingestion pipeline. Poor parsing or chunking directly degrades retrieval quality and increases hallucination risk. Phase 1 exists to ensure that by the time a query reaches the retrieval layer, the knowledge base is structured, searchable, and citation-ready — because no amount of reranking or prompt engineering can fix garbage in the index.

