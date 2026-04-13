from __future__ import annotations

from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

from app.config import get_settings


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Supabase client with service_role key. Bypasses RLS — server-side only."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for server operations."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """Supabase client with anon key. RLS-enforced."""
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set for client operations."
        )
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def reset_clients() -> None:
    get_service_client.cache_clear()
    get_anon_client.cache_clear()
