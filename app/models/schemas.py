from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


JobStatus = str  # pending | parsing | chunking | embedding | completed | failed


class IngestResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    message: str


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    file_name: str
    total_chunks: int
    processed_chunks: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    match_count: int = Field(default=5, ge=1, le=50)
    rerank: bool = Field(default=True)
    include_sources: bool = Field(default=True)
    prompt_name: Optional[str] = Field(default=None)
    stream: bool = Field(default=False)


class ChunkMetadata(BaseModel):
    source: str
    document_id: str
    page_number: Optional[int] = None
    bounding_boxes: Optional[List[List[float]]] = None
    section_heading: Optional[str] = None
    document_title: Optional[str] = None
    chunk_index: int
    total_chunks: int
    parser: str
    chunk_strategy: str
    chunk_size_tokens: int
    overlap_tokens: int

    model_config = {"extra": "allow"}


class QueryResult(BaseModel):
    id: UUID
    content: str
    metadata: dict[str, Any]
    similarity: float


class QueryResponse(BaseModel):
    query: str
    results: List[QueryResult]


class Citation(BaseModel):
    source_id: str
    chunk_id: UUID
    content: str
    metadata: dict[str, Any]
    rerank_score: Optional[float] = None
    rrf_score: Optional[float] = None


class LatencyBreakdown(BaseModel):
    embedding: int = 0
    retrieval: int = 0
    dense_retrieval: int = 0
    sparse_retrieval: int = 0
    rrf_fusion: int = 0
    reranking: int = 0
    generation: int = 0
    total: int = 0


class RetrievalMetadata(BaseModel):
    dense_results: int = 0
    sparse_results: int = 0
    rrf_candidates: int = 0
    reranked_top_k: int = 0
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    reranker_provider: Optional[str] = None
    latency_ms: LatencyBreakdown = Field(default_factory=LatencyBreakdown)


class HybridQueryResponse(BaseModel):
    query: str
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    retrieval_metadata: RetrievalMetadata
    declined: bool = False


class PromptCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    system_prompt: str = Field(..., min_length=1)
    user_prompt_template: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    global_: bool = Field(default=False, alias="global")


class PromptSummary(BaseModel):
    id: UUID
    name: str
    version: int
    is_active: bool
    tenant_id: Optional[UUID] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class PromptListResponse(BaseModel):
    prompts: List[PromptSummary]


class HealthResponse(BaseModel):
    status: str
    version: str
    supabase: str
    openai: str
    cohere: str = "not_configured"


class ParsedBlock(BaseModel):
    """A single parsed block from the document parser."""

    text: str
    page_number: Optional[int] = None
    bounding_boxes: Optional[List[List[float]]] = None
    section_heading: Optional[str] = None
    element_type: Optional[str] = None


class PreparedChunk(BaseModel):
    """Chunk with injected context and full metadata ready for embedding."""

    content: str
    metadata: ChunkMetadata
