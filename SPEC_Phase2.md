# SPEC.md — Phase 2: Hybrid Retrieval, Reranking, and Citation-Enforced Generation

---

## 1. Executive Summary

Phase 2 graduates the RAG system from a basic vector-similarity retrieval prototype into a production-quality query pipeline. The objective is to dramatically improve retrieval precision and introduce grounded, citation-enforced LLM response generation.

Phase 1 established the ingestion backbone: documents are parsed, chunked, embedded, and stored in Supabase pgvector with full spatial metadata. Phase 2 now builds the **query-time intelligence** — the logic that turns a user's natural language question into a precise, cited, and hallucination-resistant answer.

### Phase 2 Scope

- Hybrid retrieval combining dense (vector) and sparse (BM25) search
- Reciprocal Rank Fusion (RRF) to merge ranked result sets
- Cross-encoder reranking for precision refinement
- Citation-enforced LLM response generation
- Hallucination guardrails (explicit decline when context is insufficient)
- Versioned prompt management
- Extended `/query` endpoint with generation and citations

### Out of Scope (Deferred to Later Phases)

- Automated evaluation pipeline (Ragas, golden dataset) → Phase 3
- CI-gated quality thresholds → Phase 3
- AI SDK / Chat widget / Frontend delivery → Phase 4
- PDF viewer with bounding box overlays → Phase 4
- Multi-deployment architecture (API, widget, iframe) → Phase 4

---

## 2. Architectural Goals

1. **Maximize Retrieval Precision**: Combine semantic understanding (vector search) with keyword exactness (BM25) so the system handles both conceptual queries and exact-match lookups (e.g., drug codes, clause numbers, part IDs).
2. **Minimize Irrelevant Context in LLM Prompt**: Use cross-encoder reranking to filter out noise before generation, reducing hallucination risk and improving response quality.
3. **Enforce Grounded Citations**: Every claim in the generated response must map back to a specific chunk, page number, and source document. No unsupported claims.
4. **Fail Gracefully on Missing Context**: If the retrieved chunks do not contain the answer, the system explicitly declines rather than hallucinating.
5. **Maintain Multi-Tenant Isolation**: All retrieval and generation operations remain scoped by `tenant_id` via RLS.
6. **Keep Prompt Logic Auditable**: Store generation prompts as versioned configuration, not hardcoded strings.

---

## 3. Prerequisites from Phase 1

Phase 2 assumes the following Phase 1 deliverables are operational:

| Component                        | Status   | Notes                                                        |
|----------------------------------|----------|--------------------------------------------------------------|
| Ingestion pipeline               | Complete | PDF → parse → chunk → embed → Supabase upsert               |
| `documents` table with pgvector  | Complete | HNSW index on `embedding`, RLS active                        |
| `ingestion_jobs` table           | Complete | Status tracking with tenant isolation                        |
| `tenants` table                  | Complete | Multi-tenant registry                                        |
| `match_documents()` function     | Complete | Basic cosine similarity retrieval (will be extended)         |
| `/ingest` endpoint               | Complete | File upload + async pipeline trigger                         |
| `/status/{job_id}` endpoint      | Complete | Job progress polling                                         |
| `/query` endpoint                | Complete | Basic vector search (will be replaced by hybrid pipeline)    |
| Metadata schema                  | Complete | page_number, bounding_boxes, section_heading, source, etc.   |

---

## 4. Tech Stack Additions (Phase 2)

### 4.1 Retrieval Layer

| Component          | Technology                          | Rationale                                                      |
|--------------------|-------------------------------------|----------------------------------------------------------------|
| Sparse Search      | PostgreSQL `tsvector` + `ts_rank`   | Native full-text search in Supabase; no external dependency    |
| Rank Fusion        | Custom RRF implementation           | Merges dense + sparse ranked lists into unified candidate set  |

### 4.2 Reranking Layer

| Component          | Technology                                      | Rationale                                                    |
|--------------------|-------------------------------------------------|--------------------------------------------------------------|
| Cross-Encoder      | Cohere Rerank API (`rerank-english-v3.0`)       | High accuracy; managed API avoids GPU provisioning           |
| Fallback           | `cross-encoder/ms-marco-MiniLM-L-6-v2` (local) | Open-source fallback for self-hosted or cost-sensitive deployments |

### 4.3 Generation Layer

| Component          | Technology                     | Rationale                                                    |
|--------------------|--------------------------------|--------------------------------------------------------------|
| LLM                | OpenAI `gpt-4o` / `gpt-4o-mini` | Strong instruction-following for citation enforcement       |
| Prompt Management  | YAML config files              | Versioned, auditable, no-redeploy prompt updates             |
| Streaming          | Server-Sent Events (SSE)       | Token-by-token delivery for responsive UX                    |

### 4.4 New Dependencies

```
cohere>=5.0.0              # Rerank API
sentence-transformers>=2.2.0  # Local cross-encoder fallback
pyyaml>=6.0                # Prompt template management
tiktoken>=0.5.0            # Token counting for context window management
sse-starlette>=1.6.0       # SSE streaming for FastAPI
```
---

## 5. System Architecture (Phase 2 Query Pipeline)

### 5.1 High-Level Query Flow

```
┌──────────────────┐
│   User Query      │
│   (natural lang)  │
└──────┬───────────┘
│
▼
┌──────────────────┐
│  Query Embedding  │  ← OpenAI text-embedding-3-small
│                   │     (same model as ingestion)
└──────┬───────────┘
│
▼
┌──────────────────────────────────────────┐
│         Parallel Retrieval               │
│                                          │
│  ┌─────────────┐    ┌─────────────────┐  │
│  │ Dense Search │    │ Sparse Search   │  │
│  │ (pgvector    │    │ (tsvector +     │  │
│  │  cosine sim) │    │  ts_rank/BM25)  │  │
│  └──────┬──────┘    └──────┬──────────┘  │
│         │                  │             │
│         └──────┬───────────┘             │
│                ▼                         │
│  ┌─────────────────────────┐             │
│  │  Reciprocal Rank Fusion │             │
│  │  (RRF Merge)            │             │
│  └──────────┬──────────────┘             │
└─────────────┼────────────────────────────┘
│
▼
┌──────────────────┐
│  Cross-Encoder   │  ← Cohere Rerank or local cross-encoder
│  Reranking       │     Rescores top-N candidates → top-K
└──────┬───────────┘
│
▼
┌──────────────────┐
│  Context Assembly │  ← Build citation-aware prompt
│  + Prompt Build   │     Inject top-K chunks with [source_id] tags
└──────┬───────────┘
│
▼
┌──────────────────┐
│  LLM Generation  │  ← GPT-4o with citation enforcement prompt
│  (with citations)│     Streaming via SSE
└──────┬───────────┘
│
▼
┌──────────────────┐
│  Response with   │  ← Each claim tagged with chunk ID
│  Citation Anchors│     Metadata (page, bbox, source) included
└──────────────────┘
```
### 5.2 Retrieval Parameter Summary

| Parameter                  | Value     | Rationale                                                          |
|----------------------------|-----------|---------------------------------------------------------------------|
| Dense retrieval top-N      | 20        | Cast wide net for semantic matches                                  |
| Sparse retrieval top-N     | 20        | Cast wide net for keyword matches                                   |
| RRF constant `k`           | 60        | Standard value; prevents top-rank dominance                         |
| Post-RRF candidate pool    | ~20-30    | Deduplicated union of dense + sparse results                        |
| Reranker input             | Top 20    | Cross-encoder processes the top 20 RRF candidates                   |
| Final top-K to LLM         | 5         | Balances context richness vs. noise; configurable per tenant        |

---

## 6. Database Schema Extensions

### 6.1 Full-Text Search Column

Add a `tsvector` column to the existing `documents` table and a GIN index for BM25-style sparse retrieval:

```sql
-- =============================================================
-- Phase 2: Add full-text search support to documents table
-- =============================================================

-- Add tsvector column for sparse retrieval
ALTER TABLE documents
  ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

-- GIN index for fast full-text search
CREATE INDEX idx_documents_fts
  ON documents
  USING gin (fts);
```

### 6.2 Prompt Versions Table

```sql
-- =============================================================
-- Table: prompt_versions
-- Purpose: Versioned storage of generation prompts for auditability
-- =============================================================
CREATE TABLE prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
  name TEXT NOT NULL,                    -- e.g., "rag_generation_v1"
  version INTEGER NOT NULL DEFAULT 1,
  system_prompt TEXT NOT NULL,
  user_prompt_template TEXT NOT NULL,    -- Contains {context} and {query} placeholders
  metadata JSONB DEFAULT '{}',          -- Model params, temperature, etc.
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Unique constraint: one active prompt per name per tenant
CREATE UNIQUE INDEX idx_prompt_active
  ON prompt_versions (tenant_id, name)
  WHERE is_active = true;

-- RLS
ALTER TABLE prompt_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_prompts" ON prompt_versions
  FOR SELECT
  USING (
    tenant_id IS NULL  -- Global prompts accessible to all
    OR tenant_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::UUID
  );
```

### 6.3 New Function: `match_documents_hybrid`

```sql
-- =============================================================
-- Function: match_documents_hybrid
-- Purpose: Parallel dense + sparse retrieval with RRF fusion
-- =============================================================
CREATE OR REPLACE FUNCTION match_documents_hybrid(
  query_embedding VECTOR(1536),
  query_text TEXT,
  match_count INT DEFAULT 5,
  rrf_k INT DEFAULT 60,
  dense_top_n INT DEFAULT 20,
  sparse_top_n INT DEFAULT 20,
  filter_tenant_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  metadata JSONB,
  rrf_score FLOAT,
  dense_rank INT,
  sparse_rank INT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH dense AS (
    SELECT
      d.id,
      d.content,
      d.metadata,
      ROW_NUMBER() OVER (ORDER BY d.embedding <=> query_embedding) AS rank
    FROM documents d
    WHERE (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
    ORDER BY d.embedding <=> query_embedding
    LIMIT dense_top_n
  ),
  sparse AS (
    SELECT
      d.id,
      d.content,
      d.metadata,
      ROW_NUMBER() OVER (ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC) AS rank
    FROM documents d
    WHERE
      (filter_tenant_id IS NULL OR d.tenant_id = filter_tenant_id)
      AND d.fts @@ websearch_to_tsquery('english', query_text)
    ORDER BY ts_rank(d.fts, websearch_to_tsquery('english', query_text)) DESC
    LIMIT sparse_top_n
  ),
  fused AS (
    SELECT
      COALESCE(dense.id, sparse.id) AS id,
      COALESCE(dense.content, sparse.content) AS content,
      COALESCE(dense.metadata, sparse.metadata) AS metadata,
      COALESCE(1.0 / (rrf_k + dense.rank), 0) + COALESCE(1.0 / (rrf_k + sparse.rank), 0) AS rrf_score,
      dense.rank AS dense_rank,
      sparse.rank AS sparse_rank
    FROM dense
    FULL OUTER JOIN sparse ON dense.id = sparse.id
  )
  SELECT
    fused.id,
    fused.content,
    fused.metadata,
    fused.rrf_score,
    COALESCE(fused.dense_rank, 0)::INT,
    COALESCE(fused.sparse_rank, 0)::INT
  FROM fused
  ORDER BY fused.rrf_score DESC
  LIMIT match_count;
END;
$$;
```

---

## 7. Pipeline Components — Detailed Specification

### 7.1 Sparse Retrieval (BM25 via tsvector)

PostgreSQL's built-in full-text search provides BM25-equivalent ranking through `ts_rank`. This avoids adding an external search engine (Elasticsearch, Meilisearch) while staying within the Supabase ecosystem.

**How it works**:

1. The `fts` column on `documents` is a generated `tsvector` column that automatically tokenizes, stems, and indexes the `content` field.
2. At query time, the user's query is converted to a `tsquery` using `websearch_to_tsquery()`, which handles natural language input (AND/OR logic, phrase matching).
3. `ts_rank()` scores each matching document based on term frequency and inverse document frequency — functionally equivalent to BM25 for most use cases.

**Why not an external BM25 engine?**

- Supabase's native `tsvector` avoids infrastructure complexity.
- For the expected document volumes (thousands to low tens-of-thousands of chunks per tenant), PostgreSQL full-text search performs well.
- If scale demands it in later phases, this can be swapped for Elasticsearch or Typesense without changing the RRF logic.

### 7.2 Reciprocal Rank Fusion (RRF)

RRF merges the ranked lists from dense and sparse retrieval into a single candidate set without requiring score normalization.

**Formula**:

RRFScore(d) = Σ  1 / (k + rank_r(d))
r ∈ {dense, sparse}

Where:
- `rank_r(d)` is the rank of document `d` in retrieval method `r` (1-indexed)
- `k` is a smoothing constant (default: 60) that prevents top-ranked documents from dominating

**Example**:

A document ranked #1 in dense and #3 in sparse:

RRFScore = 1/(60+1) + 1/(60+3) = 0.01639 + 0.01587 = 0.03226

A document ranked #2 in dense only (not in sparse results):

RRFScore = 1/(60+2) + 0 = 0.01613

The first document wins because it appeared in both retrieval methods.

**Implementation** (Python, in case the SQL function is insufficient for complex scenarios):

```python
def reciprocal_rank_fusion(
    dense_results: list[dict],
    sparse_results: list[dict],
    k: int = 60
) -> list[dict]:
    """Fuse dense and sparse ranked lists using RRF."""
    scores = {}
    doc_map = {}

    for rank, doc in enumerate(dense_results, start=1):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        doc_map[doc_id] = doc
        doc_map[doc_id]["dense_rank"] = rank

    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank)
        if doc_id not in doc_map:
            doc_map[doc_id] = doc
        doc_map[doc_id]["sparse_rank"] = rank

    fused = []
    for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        entry = doc_map[doc_id]
        entry["rrf_score"] = score
        fused.append(entry)

    return fused
```

### 7.3 Cross-Encoder Reranking

After RRF produces a merged candidate pool (~20-30 documents), a cross-encoder reranker rescores each candidate by processing the (query, chunk) pair jointly. This is far more accurate than the independent embeddings used in the retrieval step.

**Primary: Cohere Rerank API**

```python
import cohere

co = cohere.Client(api_key=COHERE_API_KEY)

def rerank_chunks(
    query: str,
    chunks: list[dict],
    top_k: int = 5
) -> list[dict]:
    """Rerank candidate chunks using Cohere cross-encoder."""
    documents = [chunk["content"] for chunk in chunks]

    response = co.rerank(
        model="rerank-english-v3.0",
        query=query,
        documents=documents,
        top_n=top_k,
        return_documents=False,
    )

    reranked = []
    for result in response.results:
        chunk = chunks[result.index]
        chunk["rerank_score"] = result.relevance_score
        reranked.append(chunk)

    return reranked
```

**Fallback: Local Cross-Encoder**

```python
from sentence_transformers import CrossEncoder

model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank_chunks_local(
    query: str,
    chunks: list[dict],
    top_k: int = 5
) -> list[dict]:
    """Rerank using local cross-encoder model."""
    pairs = [(query, chunk["content"]) for chunk in chunks]
    scores = model.predict(pairs)

    for i, score in enumerate(scores):
        chunks[i]["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
    return reranked[:top_k]
```

**When to use which**:

| Scenario                           | Use Cohere API          | Use Local Model         |
|------------------------------------|-------------------------|-------------------------|
| Cloud SaaS deployment              | ✓ (preferred)           |                         |
| Self-hosted / air-gapped           |                         | ✓ (required)            |
| Cost-sensitive high-volume         |                         | ✓ (no per-query cost)   |
| Maximum accuracy                   | ✓ (larger model)        |                         |

### 7.4 Citation-Enforced Generation

This is the core addition of Phase 2 — the LLM generates responses that are grounded in retrieved context and include citation anchors mapping back to source metadata.

**Context Assembly**:

Before sending to the LLM, the top-K reranked chunks are formatted with unique identifiers:

```python
def assemble_context(chunks: list[dict]) -> str:
    """Build citation-aware context string for LLM prompt."""
    context_parts = []
    for i, chunk in enumerate(chunks):
        source_id = f"[SOURCE_{i+1}]"
        meta = chunk["metadata"]
        header = (
            f"{source_id}\n"
            f"Document: {meta.get('document_title', meta.get('source', 'Unknown'))}\n"
            f"Section: {meta.get('section_heading', 'N/A')}\n"
            f"Page: {meta.get('page_number', 'N/A')}\n"
            f"---\n"
            f"{chunk['content']}"
        )
        context_parts.append(header)
    return "\n\n".join(context_parts)
```

**Prompt Structure** (stored in YAML, loaded at runtime):

```yaml
# prompts/rag_generation_v1.yaml
name: rag_generation_v1
version: 1
model: gpt-4o
temperature: 0.1
max_tokens: 2048

system_prompt: |
  You are a precise, domain-expert assistant. Your sole purpose is to answer
  questions using ONLY the provided source context.

  RULES:
  1. Answer ONLY based on the provided context. Do not use prior knowledge.
  2. For every factual claim in your response, include a citation anchor
     in the format [SOURCE_N] immediately after the claim.
  3. If multiple sources support a claim, cite all of them: [SOURCE_1][SOURCE_3].
  4. If the provided context does NOT contain enough information to answer
     the question, respond EXACTLY with:
     "I don't have enough information in the available documents to answer
     this question. The following sources were searched: {sources_list}"
  5. Do not speculate, infer, or extrapolate beyond what is explicitly stated
     in the context.
  6. Preserve technical terminology exactly as it appears in the sources.
  7. If the context contains conflicting information, acknowledge the conflict
     and cite both sources.

user_prompt_template: |
  CONTEXT:
  {context}

  ---

  QUESTION: {query}

  Provide a precise answer with citations.
```

**Prompt Loading**:

```python
import yaml
from pathlib import Path

def load_prompt(name: str, tenant_id: str | None = None) -> dict:
    """Load prompt config from YAML file or database."""
    # Priority: tenant-specific DB prompt > global DB prompt > YAML file
    if tenant_id:
        db_prompt = fetch_active_prompt(tenant_id, name)
        if db_prompt:
            return db_prompt

    global_prompt = fetch_active_prompt(None, name)
    if global_prompt:
        return global_prompt

    # Fallback to YAML
    path = Path(f"prompts/{name}.yaml")
    with open(path) as f:
        return yaml.safe_load(f)
```

### 7.5 Hallucination Guardrails

The system implements two layers of hallucination defense:

**Layer 1: Relevance Threshold**

After reranking, if the top-ranked chunk's relevance score is below a configurable threshold, the system short-circuits generation and returns a "no sufficient context" response.

```python
RELEVANCE_THRESHOLD = 0.25  # Cohere rerank scores range 0-1

def check_relevance(reranked_chunks: list[dict]) -> bool:
    """Check if any chunk meets minimum relevance threshold."""
    if not reranked_chunks:
        return False
    return reranked_chunks[0]["rerank_score"] >= RELEVANCE_THRESHOLD
```

**Layer 2: Prompt-Based Decline**

The system prompt (Section 7.4) instructs the LLM to explicitly decline if context is insufficient. This acts as a second defense if the relevance threshold is too permissive.

### 7.6 Streaming Response (SSE)

For responsive UX, the generation endpoint streams tokens as they are produced:

```python
from sse_starlette.sse import EventSourceResponse
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

async def stream_generation(prompt: dict, context: str, query: str):
    """Stream LLM response token-by-token via SSE."""
    messages = [
        {"role": "system", "content": prompt["system_prompt"]},
        {"role": "user", "content": prompt["user_prompt_template"].format(
            context=context, query=query
        )},
    ]

    stream = client.chat.completions.create(
        model=prompt.get("model", "gpt-4o"),
        messages=messages,
        temperature=prompt.get("temperature", 0.1),
        max_tokens=prompt.get("max_tokens", 2048),
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield {"event": "token", "data": delta}

    yield {"event": "done", "data": ""}
```

---

## 8. API Design (Phase 2)

### 8.1 Updated Endpoints

Phase 2 replaces the basic `/query` endpoint and adds a streaming variant.

#### `POST /query` (Updated)

Full hybrid retrieval → rerank → generate pipeline. Returns a complete response with citations.

**Headers**:
- `Authorization: Bearer <jwt_token>`

**Body**:
```json
{
  "query": "What is the liability cap in the MSA?",
  "match_count": 5,
  "stream": false,
  "include_sources": true,
  "rerank": true,
  "prompt_name": "rag_generation_v1"
}
```

**Response** (`200 OK`):
```json
{
  "query": "What is the liability cap in the MSA?",
  "answer": "The liability cap shall not exceed $1,000,000 in aggregate for all claims arising under the agreement [SOURCE_1]. This limitation applies to both direct and indirect damages [SOURCE_1], and is governed by Section 3.2 of the Master Services Agreement [SOURCE_2].",
  "citations": [
    {
      "source_id": "SOURCE_1",
      "chunk_id": "uuid-chunk-1",
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
    },
    {
      "source_id": "SOURCE_2",
      "chunk_id": "uuid-chunk-2",
      "content": "Section 3.2 governs all liability...",
      "metadata": {
        "source": "contract.pdf",
        "page_number": 6,
        "bounding_boxes": [[72, 100, 540, 140]],
        "section_heading": "Section 3.2 — Limitation of Liability",
        "document_title": "Master Services Agreement"
      },
      "rerank_score": 0.88,
      "rrf_score": 0.028
    }
  ],
  "retrieval_metadata": {
    "dense_results": 20,
    "sparse_results": 12,
    "rrf_candidates": 26,
    "reranked_top_k": 5,
    "model": "gpt-4o",
    "prompt_version": "rag_generation_v1:v1",
    "latency_ms": {
      "embedding": 45,
      "dense_retrieval": 32,
      "sparse_retrieval": 18,
      "rrf_fusion": 2,
      "reranking": 380,
      "generation": 1200,
      "total": 1677
    }
  }
}
```

#### `POST /query/stream`

Same pipeline, but streams the generation step via SSE.

**Body**: Same as `/query` (the `stream` field is ignored; this endpoint always streams).

**SSE Events**:

```
event: sources
data: {"citations": [...]}    ← Sent first, before generation begins
event: token
data: "The"
event: token
data: " liability"
event: token
data: " cap"
...
event: done
data: {"retrieval_metadata": {...}}
```
The `sources` event is sent before generation begins so the frontend can pre-render citation cards while tokens stream in.

#### `GET /prompts` (New)

List available prompt templates for the authenticated tenant.

**Response** (`200 OK`):
```json
{
  "prompts": [
    {
      "name": "rag_generation_v1",
      "version": 1,
      "is_active": true,
      "model": "gpt-4o",
      "created_at": "2025-04-20T10:00:00Z"
    }
  ]
}
```

#### `POST /prompts` (New)

Create or update a prompt template. Setting `is_active: true` deactivates the previous version for that name.

**Body**:
```json
{
  "name": "rag_generation_v1",
  "system_prompt": "...",
  "user_prompt_template": "...",
  "metadata": {
    "model": "gpt-4o",
    "temperature": 0.1,
    "max_tokens": 2048
  }
}
```

### 8.2 Existing Endpoints (Unchanged)

These Phase 1 endpoints remain as-is:

- `POST /ingest` — Document upload and ingestion
- `GET /status/{job_id}` — Ingestion job polling
- `GET /health` — Health check (extended to include Cohere connectivity)

---

## 9. Pipeline Orchestrator (Phase 2 Query Pipeline)

### 9.1 Orchestration Flow

The query pipeline is orchestrated as a sequential chain using LangChain/LangGraph:

```python
from langchain_core.runnables import RunnableSequence

query_pipeline = RunnableSequence(
    embed_query,           # Step 1: Embed the user query
    hybrid_retrieve,       # Step 2: Dense + Sparse + RRF
    rerank,                # Step 3: Cross-encoder reranking
    check_relevance,       # Step 4: Hallucination guardrail
    assemble_context,      # Step 5: Build citation-aware prompt
    generate_response,     # Step 6: LLM generation with citations
    parse_citations,       # Step 7: Extract and resolve citation anchors
)
```

### 9.2 Citation Resolution

After generation, the response text is parsed to extract `[SOURCE_N]` anchors and resolve them to full metadata:

```python
import re

def resolve_citations(
    response_text: str,
    chunks: list[dict]
) -> tuple[str, list[dict]]:
    """Extract citation anchors and map to chunk metadata."""
    pattern = r'\[SOURCE_(\d+)\]'
    cited_indices = set(int(m) for m in re.findall(pattern, response_text))

    citations = []
    for idx in sorted(cited_indices):
        if 1 <= idx <= len(chunks):
            chunk = chunks[idx - 1]
            citations.append({
                "source_id": f"SOURCE_{idx}",
                "chunk_id": chunk["id"],
                "content": chunk["content"][:200] + "...",
                "metadata": chunk["metadata"],
                "rerank_score": chunk.get("rerank_score"),
                "rrf_score": chunk.get("rrf_score"),
            })

    return response_text, citations
```

---

## 10. Project Structure (Phase 2 Additions)

```
rag-ingestion/
├── app/
│   ├── api/
│   │   ├── query.py               # UPDATED: Hybrid retrieval + generation
│   │   ├── query_stream.py        # NEW: SSE streaming endpoint
│   │   └── prompts.py             # NEW: Prompt management endpoints
│   ├── pipeline/
│   │   ├── orchestrator.py        # UPDATED: Phase 2 query pipeline
│   │   ├── retriever_dense.py     # NEW: Vector similarity retrieval
│   │   ├── retriever_sparse.py    # NEW: tsvector/BM25 retrieval
│   │   ├── fusion.py              # NEW: RRF implementation
│   │   ├── reranker.py            # NEW: Cross-encoder reranking
│   │   ├── generator.py           # NEW: Citation-enforced LLM generation
│   │   └── citation_resolver.py   # NEW: Parse and resolve citation anchors
│   ├── models/
│   │   └── schemas.py             # UPDATED: New request/response models
│   └── utils/
│       └── prompt_loader.py       # NEW: YAML + DB prompt loading
├── prompts/
│   └── rag_generation_v1.yaml     # NEW: Default generation prompt
├── sql/
│   ├── schema.sql                 # Phase 1 schema (unchanged)
│   └── phase2_migration.sql       # NEW: fts column, hybrid function, prompts table
├── tests/
│   ├── test_retriever_sparse.py   # NEW
│   ├── test_fusion.py             # NEW
│   ├── test_reranker.py           # NEW
│   ├── test_generator.py          # NEW
│   ├── test_citation_resolver.py  # NEW
│   └── test_query_pipeline.py     # NEW: End-to-end query pipeline test
└── ...
```

---

## 11. Environment Variables (Phase 2 Additions)

```env
# --- Phase 1 variables remain unchanged ---

# Cohere (Reranking)
COHERE_API_KEY=...

# Generation
GENERATION_MODEL=gpt-4o             # or gpt-4o-mini for cost savings
GENERATION_TEMPERATURE=0.1
GENERATION_MAX_TOKENS=2048

# Retrieval Tuning
DENSE_TOP_N=20
SPARSE_TOP_N=20
RRF_K=60
RERANK_TOP_K=5
RELEVANCE_THRESHOLD=0.25

# Reranker Selection
RERANKER_PROVIDER=cohere             # cohere | local
LOCAL_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

# Prompt
DEFAULT_PROMPT_NAME=rag_generation_v1
```

---

## 12. Engineering Considerations

### 12.1 Performance

- **Parallel Retrieval**: Dense and sparse searches run concurrently (Python `asyncio.gather` or the SQL function handles both in a single call). This keeps retrieval latency at the slower of the two, not the sum.
- **Reranker Latency**: The Cohere API call is the single largest latency contributor (~200-500ms for 20 documents). For latency-sensitive applications, reduce the reranker input count or use the local model.
- **Streaming**: SSE streaming hides generation latency from the user. Time-to-first-token is the key metric, not total generation time.
- **Context Window Management**: With `gpt-4o` (128K context), 5 chunks of 700 tokens each uses ~3,500 tokens of context — well within limits. The prompt itself adds ~500 tokens. Total input is ~4,000 tokens per query.

### 12.2 Reliability

- **Reranker Fallback**: If Cohere API is unavailable, automatically fall back to the local cross-encoder. Log the fallback event.
- **Generation Timeout**: Set a 30-second timeout on LLM generation. If exceeded, return whatever has been generated so far (for streaming) or a timeout error (for non-streaming).
- **Empty Retrieval**: If both dense and sparse retrieval return zero results, short-circuit to a "no relevant documents found" response without calling the LLM.
- **Retry Logic**: Same exponential backoff from Phase 1 applies to Cohere and OpenAI generation calls (max 3 retries).

### 12.3 Observability

- **Per-Step Latency**: Track and return latency for each pipeline step (embedding, dense, sparse, RRF, reranking, generation) in the response metadata.
- **Citation Coverage**: Track the percentage of generated claims that include citation anchors. Low coverage suggests the prompt needs tuning.
- **Reranker Score Distribution**: Monitor the distribution of rerank scores. A consistently low max score suggests retrieval quality issues upstream.
- **Metrics to Add**:
  - Query latency (total and per-step)
  - Reranker fallback rate
  - Relevance threshold rejection rate
  - Citation anchor count per response
  - Token usage per query (input + output)

### 12.4 Cost Estimation

| Component                | Cost per Query (approx)  | Notes                              |
|--------------------------|--------------------------|-------------------------------------|
| Query embedding          | ~$0.000002               | Single embedding call               |
| Cohere rerank            | ~$0.002                  | 20 documents reranked               |
| GPT-4o generation        | ~$0.01-0.03              | ~4K input + ~500 output tokens      |
| GPT-4o-mini generation   | ~$0.001-0.003            | 10x cheaper, slightly lower quality |
| **Total (GPT-4o)**       | **~$0.012-0.032**        |                                     |
| **Total (GPT-4o-mini)**  | **~$0.003-0.005**        |                                     |

At 10,000 queries/month with GPT-4o: ~$120-320/month for generation costs.

---

## 13. Security Considerations (Phase 2)

All Phase 1 security measures remain in effect. Additional Phase 2 concerns:

- **Prompt Injection Defense**: The system prompt explicitly constrains the LLM to use only provided context. User queries are placed in the `user` role, not the `system` role. However, this is not foolproof — Phase 3 evaluation should include adversarial prompt injection tests.
- **Tenant Isolation in Generation**: The retrieval step is tenant-scoped via RLS. The LLM never sees chunks from other tenants. The `tenant_id` is never included in the prompt sent to the LLM.
- **API Key Security**: The Cohere API key is server-side only, same handling as OpenAI and LlamaParse keys.
- **Prompt Versioning Audit Trail**: The `prompt_versions` table retains all versions (deactivated prompts are not deleted), providing a full audit trail of prompt changes.

---

## 14. Deliverables (Phase 2 Completion Criteria)

| #  | Deliverable                                        | Acceptance Criteria                                                                    |
|----|----------------------------------------------------|----------------------------------------------------------------------------------------|
| 1  | Full-text search column + index                    | `fts` tsvector column on `documents`; GIN index active                                  |
| 2  | Hybrid retrieval function                          | `match_documents_hybrid` returns RRF-fused results from dense + sparse                  |
| 3  | Cross-encoder reranking                            | Cohere rerank integration with local fallback; top-K selection working                  |
| 4  | Citation-enforced generation                       | LLM responses include `[SOURCE_N]` anchors; citations resolve to chunk metadata         |
| 5  | Hallucination guardrails                           | System declines when relevance threshold not met; prompt enforces context-only answers   |
| 6  | Updated `/query` endpoint                          | Full pipeline: embed → hybrid retrieve → rerank → generate → cite                       |
| 7  | Streaming `/query/stream` endpoint                 | SSE streaming with sources sent before generation begins                                 |
| 8  | Prompt management (`/prompts` endpoints + YAML)    | Versioned prompts loadable from DB or YAML; tenant-specific overrides supported          |
| 9  | Per-step latency tracking                          | Response includes latency breakdown for each pipeline stage                              |
| 10 | Test suite for Phase 2 components                  | Unit tests for sparse retriever, RRF, reranker, generator, citation resolver             |

---

## 15. Migration Checklist

Steps to upgrade a running Phase 1 deployment to Phase 2:

1. Run `sql/phase2_migration.sql` to add the `fts` column, GIN index, `prompt_versions` table, and `match_documents_hybrid` function.
2. The `fts` column is `GENERATED ALWAYS`, so it auto-populates for all existing rows — no backfill needed.
3. Add Phase 2 environment variables (Cohere key, generation model, retrieval tuning params).
4. Install new Python dependencies (`cohere`, `sentence-transformers`, `pyyaml`, `sse-starlette`, `tiktoken`).
5. Deploy new pipeline modules and updated API endpoints.
6. Place default prompt YAML in `prompts/` directory.
7. Verify with an end-to-end test: upload a document (Phase 1), then query it (Phase 2) and confirm citations in the response.

---

## 16. Phase 3 Preview (Next Steps)

Phase 3 will build on this query pipeline by introducing:

1. **Golden Dataset Creation**: Curate 50-200 question-answer pairs with verified source grounding for evaluation.
2. **Ragas Evaluation Pipeline**: Automated measurement of faithfulness, answer relevance, context precision, and context recall.
3. **CI-Gated Quality Thresholds**: GitHub Actions integration that blocks merges if evaluation scores drop below configurable minimums (e.g., faithfulness < 0.85).
4. **Regression Detection**: Track evaluation metrics over time to detect silent quality degradation.

---

## 17. Key Insight

> Phase 1 ensured the knowledge base is structured and searchable. Phase 2 ensures the answers are precise and trustworthy. The combination of hybrid retrieval (catching what vector search misses), cross-encoder reranking (filtering noise before generation), and citation enforcement (proving every claim) is what separates a demo from a production system. Without these layers, the LLM is guessing with context; with them, it's reasoning with evidence.




