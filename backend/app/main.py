from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    auth,
    eval as eval_api,
    health,
    ingest,
    integrations,
    platform,
    prompts,
    public_v1,
    query,
    query_stream,
    status,
)
from app.config import get_settings
from app.utils.api_errors import error_payload
from app.utils.logger import configure_logging, get_logger
from app.utils.messages import get_message


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "message" in exc.detail:
            payload = exc.detail
        else:
            payload = {"message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload("common.validation_failed", detail=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_payload("common.internal_error", detail=get_message("common.internal_error")),
        )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(status.router)
    app.include_router(query.router)
    app.include_router(query_stream.router)
    app.include_router(platform.router)
    app.include_router(integrations.router)
    app.include_router(public_v1.router)
    app.include_router(prompts.router)
    app.include_router(eval_api.router)
    return app


app = create_app()
