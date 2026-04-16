from __future__ import annotations

from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


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
