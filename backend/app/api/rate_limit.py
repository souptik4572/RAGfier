from __future__ import annotations

from app.api.auth import AuthContext
from app.api.platform_auth import PlatformAuthContext
from app.config import get_settings
from app.utils.rate_limiter import get_rate_limiter


def _jwt_identity(auth: AuthContext, *, stream: bool) -> str:
    scope = "query_stream" if stream else "query"
    user_id = auth.user_id or "anonymous"
    return f"jwt:{scope}:tenant:{auth.tenant_id}:user:{user_id}"


def _api_key_identity(auth: PlatformAuthContext, *, stream: bool) -> str:
    scope = "query_stream" if stream else "query"
    return f"api_key:{scope}:tenant:{auth.tenant_id}:key:{auth.api_key_id}"


async def enforce_jwt_query_limit(auth: AuthContext) -> dict[str, str]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return {}

    return await get_rate_limiter().enforce_request_limit(
        identity_key=_jwt_identity(auth, stream=False),
        policy_name="jwt.query.requests",
        limit=settings.rate_limit_jwt_query_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )


async def enforce_jwt_stream_limits(auth: AuthContext) -> tuple[str | None, dict[str, str]]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return None, {}

    limiter = get_rate_limiter()
    request_headers = await limiter.enforce_request_limit(
        identity_key=_jwt_identity(auth, stream=True),
        policy_name="jwt.query_stream.requests",
        limit=settings.rate_limit_jwt_stream_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )
    lease_key = await limiter.enforce_stream_concurrency(
        identity_key=_jwt_identity(auth, stream=True),
        policy_name="jwt.query_stream.concurrency",
        max_slots=settings.rate_limit_jwt_stream_concurrency,
        ttl_seconds=settings.rate_limit_stream_slot_ttl_seconds,
    )
    return lease_key, request_headers


async def enforce_api_key_query_limit(auth: PlatformAuthContext) -> dict[str, str]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return {}

    return await get_rate_limiter().enforce_request_limit(
        identity_key=_api_key_identity(auth, stream=False),
        policy_name="api_key.query.requests",
        limit=settings.rate_limit_api_key_query_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )


async def enforce_api_key_stream_limits(auth: PlatformAuthContext) -> tuple[str | None, dict[str, str]]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return None, {}

    limiter = get_rate_limiter()
    request_headers = await limiter.enforce_request_limit(
        identity_key=_api_key_identity(auth, stream=True),
        policy_name="api_key.query_stream.requests",
        limit=settings.rate_limit_api_key_stream_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )
    lease_key = await limiter.enforce_stream_concurrency(
        identity_key=_api_key_identity(auth, stream=True),
        policy_name="api_key.query_stream.concurrency",
        max_slots=settings.rate_limit_api_key_stream_concurrency,
        ttl_seconds=settings.rate_limit_stream_slot_ttl_seconds,
    )
    return lease_key, request_headers


async def enforce_jwt_ingest_limit(auth: AuthContext) -> dict[str, str]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return {}

    user_id = auth.user_id or "anonymous"
    identity_key = f"jwt:ingest:tenant:{auth.tenant_id}:user:{user_id}"
    return await get_rate_limiter().enforce_request_limit(
        identity_key=identity_key,
        policy_name="jwt.ingest.requests",
        limit=settings.rate_limit_jwt_ingest_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )


async def enforce_api_key_ingest_limit(auth: PlatformAuthContext) -> dict[str, str]:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return {}

    identity_key = f"api_key:ingest:tenant:{auth.tenant_id}:key:{auth.api_key_id}"
    return await get_rate_limiter().enforce_request_limit(
        identity_key=identity_key,
        policy_name="api_key.ingest.requests",
        limit=settings.rate_limit_api_key_ingest_requests_per_window,
        window_seconds=settings.rate_limit_window_seconds,
    )


async def release_stream_limit_lease(lease_key: str | None) -> None:
    await get_rate_limiter().release_stream_concurrency(lease_key=lease_key)
