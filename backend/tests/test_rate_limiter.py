from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.utils.rate_limiter import MemoryRateLimiterBackend, RateLimiter


@pytest.mark.asyncio
async def test_request_window_blocks_when_limit_exceeded() -> None:
    limiter = RateLimiter(backend=MemoryRateLimiterBackend(), fail_open=False)

    await limiter.enforce_request_limit(
        identity_key="tenant:t1:user:u1",
        policy_name="test.requests",
        limit=1,
        window_seconds=60,
    )

    with pytest.raises(HTTPException) as exc:
        await limiter.enforce_request_limit(
            identity_key="tenant:t1:user:u1",
            policy_name="test.requests",
            limit=1,
            window_seconds=60,
        )

    assert exc.value.status_code == 429
    assert exc.value.headers is not None
    assert "Retry-After" in exc.value.headers


@pytest.mark.asyncio
async def test_stream_concurrency_releases_slot() -> None:
    limiter = RateLimiter(backend=MemoryRateLimiterBackend(), fail_open=False)

    lease = await limiter.enforce_stream_concurrency(
        identity_key="tenant:t1:key:k1",
        policy_name="test.streams",
        max_slots=1,
        ttl_seconds=60,
    )
    assert lease == "tenant:t1:key:k1"

    with pytest.raises(HTTPException) as exc:
        await limiter.enforce_stream_concurrency(
            identity_key="tenant:t1:key:k1",
            policy_name="test.streams",
            max_slots=1,
            ttl_seconds=60,
        )
    assert exc.value.status_code == 429

    await limiter.release_stream_concurrency(lease_key=lease)

    new_lease = await limiter.enforce_stream_concurrency(
        identity_key="tenant:t1:key:k1",
        policy_name="test.streams",
        max_slots=1,
        ttl_seconds=60,
    )
    assert new_lease == "tenant:t1:key:k1"
