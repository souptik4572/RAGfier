from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.config import get_settings
from app.utils.api_errors import raise_api_error
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int
    remaining: int


class RateLimiterBackend(Protocol):
    async def consume_window(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision: ...

    async def acquire_stream_slot(
        self,
        *,
        key: str,
        max_slots: int,
        ttl_seconds: int,
    ) -> RateLimitDecision: ...

    async def release_stream_slot(self, *, key: str) -> None: ...


class MemoryRateLimiterBackend:
    def __init__(self) -> None:
        self._window_counts: dict[tuple[str, int], int] = {}
        self._stream_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def consume_window(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        now = int(time.time())
        window_id = now // max(window_seconds, 1)
        bucket = (key, window_id)

        async with self._lock:
            current = self._window_counts.get(bucket, 0) + 1
            self._window_counts[bucket] = current

        remaining = max(limit - current, 0)
        retry_after = max(((window_id + 1) * window_seconds) - now, 1)
        return RateLimitDecision(
            allowed=current <= limit,
            retry_after_seconds=retry_after,
            remaining=remaining,
        )

    async def acquire_stream_slot(
        self,
        *,
        key: str,
        max_slots: int,
        ttl_seconds: int,
    ) -> RateLimitDecision:
        del ttl_seconds
        async with self._lock:
            current = self._stream_counts.get(key, 0) + 1
            if current > max_slots:
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=1,
                    remaining=0,
                )
            self._stream_counts[key] = current
            return RateLimitDecision(
                allowed=True,
                retry_after_seconds=0,
                remaining=max(max_slots - current, 0),
            )

    async def release_stream_slot(self, *, key: str) -> None:
        async with self._lock:
            current = self._stream_counts.get(key, 0)
            if current <= 1:
                self._stream_counts.pop(key, None)
                return
            self._stream_counts[key] = current - 1


class RedisRateLimiterBackend:
    def __init__(self, *, redis_url: str, connect_timeout_ms: int) -> None:
        self._redis_url = redis_url
        self._connect_timeout_ms = connect_timeout_ms
        self._client = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self):
        if self._client is not None:
            return self._client

        async with self._client_lock:
            if self._client is not None:
                return self._client

            try:
                import redis.asyncio as redis  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - env specific
                raise RuntimeError("redis package is not installed") from exc

            self._client = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=max(self._connect_timeout_ms, 1) / 1000,
            )
            return self._client

    async def consume_window(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        client = await self._get_client()
        redis_key = f"rl:window:{key}:{window_seconds}"

        count = int(await client.incr(redis_key))
        if count == 1:
            await client.expire(redis_key, window_seconds)

        ttl = int(await client.ttl(redis_key))
        if ttl < 1:
            ttl = max(window_seconds, 1)

        return RateLimitDecision(
            allowed=count <= limit,
            retry_after_seconds=ttl,
            remaining=max(limit - count, 0),
        )

    async def acquire_stream_slot(
        self,
        *,
        key: str,
        max_slots: int,
        ttl_seconds: int,
    ) -> RateLimitDecision:
        client = await self._get_client()
        redis_key = f"rl:stream:{key}"

        count = int(await client.incr(redis_key))
        await client.expire(redis_key, max(ttl_seconds, 1))
        if count > max_slots:
            await client.decr(redis_key)
            ttl = int(await client.ttl(redis_key))
            if ttl < 1:
                ttl = 1
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=ttl,
                remaining=0,
            )

        return RateLimitDecision(
            allowed=True,
            retry_after_seconds=0,
            remaining=max(max_slots - count, 0),
        )

    async def release_stream_slot(self, *, key: str) -> None:
        client = await self._get_client()
        redis_key = f"rl:stream:{key}"
        count = int(await client.decr(redis_key))
        if count <= 0:
            await client.delete(redis_key)


class RateLimiter:
    def __init__(self, *, backend: RateLimiterBackend, fail_open: bool) -> None:
        self._backend = backend
        self._fail_open = fail_open

    async def enforce_request_limit(
        self,
        *,
        identity_key: str,
        policy_name: str,
        limit: int,
        window_seconds: int,
    ) -> dict[str, str]:
        if limit <= 0:
            return {}

        decision = await self._safe_call(
            self._backend.consume_window(
                key=identity_key,
                limit=limit,
                window_seconds=window_seconds,
            )
        )
        if decision is None:
            return {}

        headers = self._headers_for_decision(decision=decision, limit=limit)
        if decision.allowed:
            return headers

        raise_api_error(
            429,
            "common.rate_limited",
            detail={
                "policy": policy_name,
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                **headers,
            },
        )

    async def enforce_stream_concurrency(
        self,
        *,
        identity_key: str,
        policy_name: str,
        max_slots: int,
        ttl_seconds: int,
    ) -> str | None:
        if max_slots <= 0:
            return None

        decision = await self._safe_call(
            self._backend.acquire_stream_slot(
                key=identity_key,
                max_slots=max_slots,
                ttl_seconds=ttl_seconds,
            )
        )
        if decision is None:
            return None
        if decision.allowed:
            return identity_key

        headers = self._headers_for_decision(decision=decision, limit=max_slots)

        raise_api_error(
            429,
            "common.rate_limited",
            detail={
                "policy": policy_name,
                "max_streams": max_slots,
                "retry_after_seconds": decision.retry_after_seconds,
            },
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                **headers,
            },
        )

    async def release_stream_concurrency(self, *, lease_key: str | None) -> None:
        if not lease_key:
            return
        await self._safe_call(self._backend.release_stream_slot(key=lease_key))

    async def _safe_call(self, awaitable):
        try:
            return await awaitable
        except Exception as exc:  # pragma: no cover - defensive path
            if self._fail_open:
                logger.warning("rate_limit.backend_failed", error=str(exc))
                return None
            raise

    def _headers_for_decision(self, *, decision: RateLimitDecision, limit: int) -> dict[str, str]:
        reset_at_epoch = int(time.time()) + max(decision.retry_after_seconds, 0)
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(decision.remaining, 0)),
            "X-RateLimit-Reset": str(reset_at_epoch),
        }


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    settings = get_settings()
    if settings.rate_limit_backend == "redis":
        backend: RateLimiterBackend = RedisRateLimiterBackend(
            redis_url=settings.effective_rate_limit_redis_url,
            connect_timeout_ms=settings.rate_limit_redis_connect_timeout_ms,
        )
    else:
        backend = MemoryRateLimiterBackend()

    return RateLimiter(backend=backend, fail_open=settings.rate_limit_fail_open)


def reset_rate_limiter() -> None:
    get_rate_limiter.cache_clear()
