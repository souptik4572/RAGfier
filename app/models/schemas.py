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
    message: str
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
    message: str
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
    message: str
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


class TenantSignupRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    tenant_name: str = Field(..., min_length=1)
    tenant_slug: Optional[str] = Field(default=None, min_length=1)


class TenantLoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class AuthTokenResponse(BaseModel):
    message: str = ""
    access_token: str
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    tenant_id: UUID
    user_id: Optional[str] = None
    email: Optional[str] = None


class PromptSummary(BaseModel):
    message: str = ""
    id: UUID
    name: str
    version: int
    is_active: bool
    tenant_id: Optional[UUID] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class PromptListResponse(BaseModel):
    message: str
    prompts: List[PromptSummary]


class HealthResponse(BaseModel):
    message: str
    status: str
    version: str
    supabase: str
    openai: str
    cohere: str = "not_configured"


class EvalRunRequest(BaseModel):
    dataset_version: Optional[str] = Field(default=None)
    tenant_id: Optional[UUID] = Field(default=None)
    trigger: str = Field(default="manual")


class EvalRunAcceptedResponse(BaseModel):
    message: str
    eval_run_id: UUID
    status: str


class EvalRunScores(BaseModel):
    faithfulness_avg: Optional[float] = None
    answer_relevancy_avg: Optional[float] = None
    context_precision_avg: Optional[float] = None
    context_recall_avg: Optional[float] = None
    citation_coverage_avg: Optional[float] = None
    decline_accuracy_avg: Optional[float] = None
    latency_compliance_avg: Optional[float] = None


class EvalRunSummary(BaseModel):
    id: UUID
    dataset_version: str
    trigger: str
    git_sha: Optional[str] = None
    git_branch: Optional[str] = None
    status: str
    passed: Optional[bool] = None
    scores: EvalRunScores
    total_samples: int = 0
    failed_samples: int = 0
    created_at: Optional[datetime] = None


class EvalRunListResponse(BaseModel):
    message: str
    runs: List[EvalRunSummary]


class EvalSampleScores(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    citation_coverage: Optional[float] = None
    decline_accuracy: Optional[float] = None


class EvalSampleResult(BaseModel):
    sample_id: str
    category: Optional[str] = None
    user_input: str
    response: str
    scores: EvalSampleScores
    passed: Optional[bool] = None
    failure_reasons: List[Any] = Field(default_factory=list)


class EvalSampleListResponse(BaseModel):
    message: str
    run_id: UUID
    samples: List[EvalSampleResult]


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
