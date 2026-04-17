from __future__ import annotations

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        json_file="config/config.defaults.json",
        json_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
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
    messages_file: str = Field(default="config/messages.json", alias="MESSAGES_FILE")

    # --- Phase 4: hosted platform + SDK ---
    platform_api_key_secret: str = Field(
        default="dev-platform-api-key-secret",
        alias="PLATFORM_API_KEY_SECRET",
    )
    platform_api_key_prefix: str = Field(default="rag_pk", alias="PLATFORM_API_KEY_PREFIX")
    platform_encryption_key: str = Field(default="", alias="PLATFORM_ENCRYPTION_KEY")
    platform_default_base_url: str = Field(
        default="http://localhost:8000",
        alias="PLATFORM_DEFAULT_BASE_URL",
    )

    # --- Phase 3: evaluation pipeline ---
    eval_dataset_path: str = Field(
        default="eval/datasets/golden_v1.0.0.json", alias="EVAL_DATASET_PATH"
    )
    eval_thresholds_path: str = Field(
        default="eval/config/thresholds.yaml", alias="EVAL_THRESHOLDS_PATH"
    )
    eval_llm_judge: str = Field(default="gpt-4o-mini", alias="EVAL_LLM_JUDGE")
    eval_faithfulness_llm: str = Field(default="gpt-4o", alias="EVAL_FAITHFULNESS_LLM")
    eval_timeout_seconds: int = Field(default=300, alias="EVAL_TIMEOUT_SECONDS")
    eval_max_concurrency: int = Field(default=5, alias="EVAL_MAX_CONCURRENCY")
    eval_latency_budget_ms: int = Field(default=5000, alias="EVAL_LATENCY_BUDGET_MS")
    eval_reports_dir: str = Field(default="eval/reports", alias="EVAL_REPORTS_DIR")

    eval_threshold_faithfulness: float = Field(default=0.85, alias="EVAL_THRESHOLD_FAITHFULNESS")
    eval_threshold_answer_relevancy: float = Field(default=0.80, alias="EVAL_THRESHOLD_ANSWER_RELEVANCY")
    eval_threshold_context_precision: float = Field(default=0.75, alias="EVAL_THRESHOLD_CONTEXT_PRECISION")
    eval_threshold_context_recall: float = Field(default=0.75, alias="EVAL_THRESHOLD_CONTEXT_RECALL")
    eval_threshold_citation_coverage: float = Field(default=0.90, alias="EVAL_THRESHOLD_CITATION_COVERAGE")
    eval_threshold_decline_accuracy: float = Field(default=0.80, alias="EVAL_THRESHOLD_DECLINE_ACCURACY")
    eval_threshold_latency_compliance: float = Field(default=0.90, alias="EVAL_THRESHOLD_LATENCY_COMPLIANCE")

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
