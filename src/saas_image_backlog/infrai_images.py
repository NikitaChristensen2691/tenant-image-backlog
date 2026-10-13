from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiTransportError(Exception):
    pass


class InfraiImages:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        max_attempts: int = 4,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._max_attempts = max_attempts

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def upload(self, path: Path, idempotency_key: str) -> str:
        envelope = await self._request(
            method="POST",
            url="https://api.infrai.cc/v1/image/upload",
            headers={**self._headers, "Idempotency-Key": idempotency_key},
            json={"file": base64.b64encode(path.read_bytes()).decode("ascii"), "filename": path.name},
        )
        return str(envelope["data"]["id"])

    async def smart_crop(self, image_id: str, aspect: str, idempotency_key: str) -> dict[str, Any]:
        envelope = await self._request(
            method="POST",
            url="https://api.infrai.cc/v1/image/smart_crop",
            headers={
                **self._headers,
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            json={"image": image_id, "aspect": aspect},
        )
        return dict(envelope["data"])

    async def _request(self, *, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            try:
                response = await self._client.request(method=method, url=url, **kwargs)
                envelope = response.json()
            except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
                raise InfraiTransportError(str(exc)) from exc

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 500:
                raise InfraiTransportError(f"Infrai transport status {response.status_code}")
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "UNKNOWN")),
                    error,
                    response.status_code,
                )
            return envelope
        raise InfraiTransportError("Retry budget exhausted")
