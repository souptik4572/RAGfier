from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PromptNotFoundError(LookupError):
    """Raised when a prompt cannot be found in DB or YAML sources."""


def _resolve_setting_reference(value: Any) -> Any:
    """Resolve `${settings_key}` placeholders against app settings.

    This keeps prompt YAML concise while centralizing runtime defaults in
    the shared config source (env/.env/JSON settings).
    """
    if not isinstance(value, str):
        return value
    if not (value.startswith("${") and value.endswith("}")):
        return value

    key = value[2:-1].strip()
    if not key:
        return value

    settings = get_settings()
    if not hasattr(settings, key):
        logger.warning("prompt_loader.unknown_setting_ref", setting_key=key)
        return value
    return getattr(settings, key)


def _prompts_dir() -> Path:
    settings = get_settings()
    base = Path(settings.prompts_dir)
    if not base.is_absolute():
        base = Path(__file__).resolve().parents[2] / base
    return base


@lru_cache(maxsize=32)
def load_yaml_prompt(name: str) -> Dict[str, Any]:
    path = _prompts_dir() / f"{name}.yaml"
    if not path.exists():
        raise PromptNotFoundError(f"Prompt YAML not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise PromptNotFoundError(f"Prompt YAML is not a mapping: {path}")
    return data


def _normalize_db_prompt(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = row.get("metadata") or {}
    return {
        "id": row.get("id"),
        "name": row["name"],
        "version": row.get("version", 1),
        "system_prompt": row["system_prompt"],
        "user_prompt_template": row["user_prompt_template"],
        "metadata": meta,
        "model": meta.get("model"),
        "temperature": meta.get("temperature"),
        "max_tokens": meta.get("max_tokens"),
        "source": "database",
        "tenant_id": row.get("tenant_id"),
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
    }


def fetch_active_prompt(
    client: Any,
    name: str,
    tenant_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Look up the active prompt row for ``(tenant_id, name)`` in Supabase.

    Returns ``None`` if no matching active row exists. Exceptions from the
    database client are swallowed and logged so the caller can fall back to
    the YAML file.
    """
    try:
        query = (
            client.table("prompt_versions")
            .select("*")
            .eq("name", name)
            .eq("is_active", True)
        )
        if tenant_id is None:
            query = query.is_("tenant_id", "null") if hasattr(query, "is_") else query.eq(
                "tenant_id", None
            )
        else:
            query = query.eq("tenant_id", tenant_id)
        response = query.limit(1).execute()
    except Exception as exc:
        logger.warning("prompt_loader.db_lookup_failed", name=name, error=str(exc))
        return None

    rows = response.data or []
    if not rows:
        return None
    return _normalize_db_prompt(rows[0])


def load_prompt(
    name: str,
    tenant_id: Optional[str] = None,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Load a prompt config with tenant > global > YAML precedence."""
    if client is not None:
        if tenant_id:
            tenant_prompt = fetch_active_prompt(client, name, tenant_id)
            if tenant_prompt:
                return tenant_prompt
        global_prompt = fetch_active_prompt(client, name, None)
        if global_prompt:
            return global_prompt

    data = load_yaml_prompt(name)
    model = _resolve_setting_reference(data.get("model"))
    temperature = _resolve_setting_reference(data.get("temperature"))
    max_tokens = _resolve_setting_reference(data.get("max_tokens"))
    return {
        "id": None,
        "name": data.get("name", name),
        "version": data.get("version", 1),
        "system_prompt": data["system_prompt"],
        "user_prompt_template": data["user_prompt_template"],
        "metadata": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "source": "yaml",
        "tenant_id": None,
        "is_active": True,
        "created_at": None,
    }


def clear_prompt_cache() -> None:
    load_yaml_prompt.cache_clear()
