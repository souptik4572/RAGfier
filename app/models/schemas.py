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


class HealthResponse(BaseModel):
    status: str
    version: str
    supabase: str
    openai: str


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
