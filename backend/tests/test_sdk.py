from __future__ import annotations

import uuid

import httpx
import pytest

from sdk.python.ragfier_sdk import RagfierSDK
from tests.test_platform_api import (
    TENANT_ID,
    _create_api_key,
    _doc,
    client as client,
    fake_db as fake_db,
)


@pytest.mark.asyncio
async def test_sdk_query_and_error_paths(client) -> None:
    sync_client = client
    secret, integration_id = _create_api_key(sync_client, return_integration_id=True)
    kb_resp = sync_client.post(
        "/v1/knowledge-bases",
        json={"name": "SDK KB"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    kb_id = kb_resp.json()["id"]

    from app.api import public_v1 as public_v1_module

    fake_db = public_v1_module.get_service_client()
    job_id = str(uuid.uuid4())
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": TENANT_ID,
            "integration_id": integration_id,
            "knowledge_base_id": kb_id,
            "file_name": "sdk.pdf",
            "file_path": "local://sdk.pdf",
            "status": "completed",
            "processed_chunks": 1,
            "total_chunks": 1,
            "created_at": "2026-04-16T10:00:00+00:00",
            "updated_at": "2026-04-16T10:01:00+00:00",
        }
    ).execute()
    fake_db.table("documents").insert(_doc(job_id, kb_id, integration_id=integration_id)).execute()

    transport = httpx.ASGITransport(app=sync_client.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        sdk = RagfierSDK(api_key=secret, base_url="http://testserver", client=http_client)
        response = await sdk.query(
            query="What is the liability cap?",
            match_count=2,
        )
        assert response["answer"].startswith("The liability cap")
