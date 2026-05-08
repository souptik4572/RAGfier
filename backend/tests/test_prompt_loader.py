from __future__ import annotations

from app.utils import prompt_loader
from app.utils.prompt_loader import clear_prompt_cache, load_prompt
from tests.fakes import FakeSupabaseClient


def test_load_yaml_fallback_returns_default_prompt() -> None:
    clear_prompt_cache()
    prompt = load_prompt("rag_generation_v1", tenant_id=None, client=None)
    assert prompt["source"] == "yaml"
    assert "{context}" in prompt["user_prompt_template"]
    assert "{query}" in prompt["user_prompt_template"]
    assert prompt["system_prompt"]


def test_load_prefers_tenant_db_row_over_yaml() -> None:
    clear_prompt_cache()
    fake = FakeSupabaseClient()
    tenant_id = "11111111-1111-1111-1111-111111111111"
    fake.table("prompt_versions").insert(
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "tenant_id": tenant_id,
            "name": "rag_generation_v1",
            "version": 2,
            "system_prompt": "tenant system",
            "user_prompt_template": "tenant user {context} {query}",
            "metadata": {"model": "gpt-4o-mini", "temperature": 0.0, "max_tokens": 128},
            "is_active": True,
            "created_at": "2026-04-13T10:00:00+00:00",
        }
    ).execute()

    prompt = load_prompt("rag_generation_v1", tenant_id=tenant_id, client=fake)
    assert prompt["source"] == "database"
    assert prompt["system_prompt"] == "tenant system"
    assert prompt["model"] == "gpt-4o-mini"
    assert prompt["version"] == 2


def test_load_falls_back_to_global_when_tenant_row_missing() -> None:
    clear_prompt_cache()
    fake = FakeSupabaseClient()
    fake.table("prompt_versions").insert(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "tenant_id": None,
            "name": "rag_generation_v1",
            "version": 1,
            "system_prompt": "global system",
            "user_prompt_template": "global {context} {query}",
            "metadata": {"model": "gpt-4o"},
            "is_active": True,
        }
    ).execute()
    prompt = load_prompt(
        "rag_generation_v1",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client=fake,
    )
    assert prompt["source"] == "database"
    assert prompt["system_prompt"] == "global system"


def test_prompt_version_is_2() -> None:
    clear_prompt_cache()
    prompt = load_prompt("rag_generation_v1", tenant_id=None, client=None)
    assert prompt["version"] == 2


def test_prompt_system_prompt_contains_decline_examples() -> None:
    clear_prompt_cache()
    prompt = load_prompt("rag_generation_v1", tenant_id=None, client=None)
    assert "DECLINE EXAMPLES" in prompt["system_prompt"]
    assert "favourite colour" in prompt["system_prompt"]
    assert "section 50" in prompt["system_prompt"]
    assert "admin password" in prompt["system_prompt"]
    # also assert decline response phrases are present
    assert "I don't have enough information in the available documents" in prompt["system_prompt"]
    assert "I was unable to find" in prompt["system_prompt"]
    assert "I'm only able to answer" in prompt["system_prompt"]
