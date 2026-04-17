from __future__ import annotations

import json
from typing import Any, AsyncIterator, BinaryIO, Optional

import httpx


class RagfierSDKError(RuntimeError):
    def __init__(self, status_code: int, message: str, detail: Any = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class RagfierSDK:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def query(self, **payload: Any) -> dict[str, Any]:
        response = await self._client.post("/v1/query", json=payload, headers=self._headers)
        return await self._decode_json(response)

    async def list_knowledge_bases(self) -> dict[str, Any]:
        response = await self._client.get("/v1/knowledge-bases", headers=self._headers)
        return await self._decode_json(response)

    async def get_job(self, job_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/jobs/{job_id}", headers=self._headers)
        return await self._decode_json(response)

    async def trigger_sync(self, connector_id: str) -> dict[str, Any]:
        response = await self._client.post(
            f"/v1/connectors/{connector_id}/sync",
            headers=self._headers,
        )
        return await self._decode_json(response)

    async def upload_document(
        self,
        *,
        knowledge_base_id: str,
        filename: str,
        content: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        document_title: str | None = None,
    ) -> dict[str, Any]:
        files = {"file": (filename, content, content_type)}
        data = {"knowledge_base_id": knowledge_base_id}
        if document_title:
            data["document_title"] = document_title
        response = await self._client.post(
            "/v1/documents/upload",
            headers=self._headers,
            data=data,
            files=files,
        )
        return await self._decode_json(response)

    async def query_stream(self, **payload: Any) -> AsyncIterator[dict[str, Any] | str]:
        async with self._client.stream(
            "POST",
            "/v1/query/stream",
            json=payload,
            headers=self._headers,
        ) as response:
            await self._raise_for_status(response)
            current_event = ""
            async for line in response.aiter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    if current_event in {"sources", "done", "error"}:
                        yield json.loads(data)
                    else:
                        yield data

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _decode_json(self, response: httpx.Response) -> dict[str, Any]:
        await self._raise_for_status(response)
        return response.json()

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            payload = response.json()
        except Exception:
            payload = {"message": response.text}
        raise RagfierSDKError(
            response.status_code,
            str(payload.get("message") or "Request failed"),
            payload.get("detail"),
        )
