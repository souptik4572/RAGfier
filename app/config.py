from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_storage_bucket: str = Field(default="documents", alias="SUPABASE_STORAGE_BUCKET")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    llama_cloud_api_key: str = Field(default="", alias="LLAMA_CLOUD_API_KEY")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    max_file_size_mb: int = Field(default=50, alias="MAX_FILE_SIZE_MB")
    allowed_file_types: Annotated[List[str], NoDecode] = Field(
        default=["pdf", "md"], alias="ALLOWED_FILE_TYPES"
    )

    chunk_size_tokens: int = Field(default=700, alias="CHUNK_SIZE_TOKENS")
    chunk_overlap_tokens: int = Field(default=100, alias="CHUNK_OVERLAP_TOKENS")
    embedding_batch_size: int = Field(default=100, alias="EMBEDDING_BATCH_SIZE")
    embedding_dimensions: int = 1536

    signed_url_expiry_seconds: int = Field(default=3600, alias="SIGNED_URL_EXPIRY_SECONDS")

    # --- Phase 2: hybrid retrieval, reranking, generation ---
    cohere_api_key: str = Field(default="", alias="COHERE_API_KEY")

    generation_model: str = Field(default="gpt-4o", alias="GENERATION_MODEL")
    generation_temperature: float = Field(default=0.1, alias="GENERATION_TEMPERATURE")
    generation_max_tokens: int = Field(default=2048, alias="GENERATION_MAX_TOKENS")
    generation_timeout_seconds: float = Field(default=30.0, alias="GENERATION_TIMEOUT_SECONDS")

    dense_top_n: int = Field(default=20, alias="DENSE_TOP_N")
    sparse_top_n: int = Field(default=20, alias="SPARSE_TOP_N")
    rrf_k: int = Field(default=60, alias="RRF_K")
    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K")
    relevance_threshold: float = Field(default=0.25, alias="RELEVANCE_THRESHOLD")

    reranker_provider: str = Field(default="cohere", alias="RERANKER_PROVIDER")
    local_reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        alias="LOCAL_RERANKER_MODEL",
    )

    default_prompt_name: str = Field(
        default="rag_generation_v1", alias="DEFAULT_PROMPT_NAME"
    )
    prompts_dir: str = Field(default="prompts", alias="PROMPTS_DIR")

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        return v

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
