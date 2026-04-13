from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api import health, ingest, prompts, query, query_stream, status
from app.config import get_settings
from app.utils.logger import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger = get_logger(__name__)
    settings = get_settings()
    logger.info(
        "app.startup",
        version=settings.app_version,
        env=settings.app_env,
    )
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RAGfier API",
        description="Multi-tenant RAG system: hybrid retrieval, reranking, and citation-enforced generation.",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(status.router)
    app.include_router(query.router)
    app.include_router(query_stream.router)
    app.include_router(prompts.router)
    return app


app = create_app()
