from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.models.schemas import AuditLogEntry, UsageBucket
from app.utils.api_errors import raise_api_error
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def write_audit_log_async(client: Any, **kwargs: Any) -> None:
    """Async wrapper — offloads the blocking Supabase insert to a worker
    thread so the request handler's event loop stays responsive to other
    in-flight requests while the audit row is written."""
    await asyncio.to_thread(write_audit_log, client, **kwargs)


async def write_request_log_async(client: Any, **kwargs: Any) -> None:
    """Async wrapper for :func:`write_request_log` — see rationale above."""
    await asyncio.to_thread(write_request_log, client, **kwargs)


def write_audit_log(
    client: Any,
    *,
    tenant_id: str,
    actor_type: str,
    action: str,
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    try:
        client.table("audit_logs").insert(
            {
                "tenant_id": tenant_id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception as exc:  # pragma: no cover - non-fatal
        logger.warning("platform.audit_log_failed", tenant_id=tenant_id, action=action, error=str(exc))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return None


def _select_tenant_rows(
    client: Any, table: str, *, tenant_id: str, limit: int
) -> list[dict[str, Any]]:
    try:
        return (
            client.table(table)
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.error("platform.select_failed", table=table, tenant_id=tenant_id, error=str(exc))
        raise_api_error(500, "common.internal_error")


def aggregate_usage_buckets(
    client: Any, *, tenant_id: str, days: int
) -> list[UsageBucket]:
    """Aggregate ``request_logs`` rows into per-day usage buckets for a tenant.

    Cap at ~100 rows/day × requested window — previously pulled the entire
    request_logs table for the tenant and re-sliced in Python.
    """
    rows = _select_tenant_rows(client, "request_logs", tenant_id=tenant_id, limit=days * 100)
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "window_start": None,
        "request_count": 0,
        "success_count": 0,
        "error_count": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "latency_total": 0,
    })
    for row in rows:
        key = str(row.get("created_at") or "")[:10]
        bucket = buckets[key]
        bucket["window_start"] = _coerce_datetime(row.get("created_at"))
        bucket["request_count"] += 1
        bucket["success_count"] += 1 if int(row.get("status_code") or 0) < 400 else 0
        bucket["error_count"] += 1 if int(row.get("status_code") or 0) >= 400 else 0
        bucket["total_input_tokens"] += int(row.get("input_tokens") or 0)
        bucket["total_output_tokens"] += int(row.get("output_tokens") or 0)
        bucket["latency_total"] += int(row.get("latency_ms") or 0)

    usage_buckets: list[UsageBucket] = []
    for bucket in buckets.values():
        count = bucket["request_count"] or 1
        usage_buckets.append(
            UsageBucket(
                window_start=bucket["window_start"],
                request_count=bucket["request_count"],
                success_count=bucket["success_count"],
                error_count=bucket["error_count"],
                total_input_tokens=bucket["total_input_tokens"],
                total_output_tokens=bucket["total_output_tokens"],
                avg_latency_ms=round(bucket["latency_total"] / count, 2),
            )
        )
    usage_buckets.sort(key=lambda item: item.window_start.isoformat() if item.window_start else "")
    return usage_buckets


def list_audit_log_entries(
    client: Any, *, tenant_id: str, limit: int
) -> list[AuditLogEntry]:
    rows = _select_tenant_rows(client, "audit_logs", tenant_id=tenant_id, limit=limit)
    return [
        AuditLogEntry(
            id=UUID(str(row["id"])),
            tenant_id=UUID(str(row["tenant_id"])),
            actor_type=str(row["actor_type"]),
            actor_id=row.get("actor_id"),
            action=str(row["action"]),
            resource_type=row.get("resource_type"),
            resource_id=row.get("resource_id"),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at"),
        )
        for row in rows
    ]


def write_request_log(
    client: Any,
    *,
    tenant_id: str,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int,
    integration_id: Optional[str] = None,
    api_key_id: Optional[str] = None,
    actor_type: str = "api_key",
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_code: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    try:
        client.table("request_logs").insert(
            {
                "tenant_id": tenant_id,
                "integration_id": integration_id,
                "api_key_id": api_key_id,
                "actor_type": actor_type,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_code": error_code,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception as exc:  # pragma: no cover - non-fatal
        logger.warning(
            "platform.request_log_failed",
            tenant_id=tenant_id,
            endpoint=endpoint,
            error=str(exc),
        )
