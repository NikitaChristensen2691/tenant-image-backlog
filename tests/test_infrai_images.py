import asyncio
import base64
import json

import httpx

from saas_image_backlog.infrai_images import InfraiImages


def test_upload_sends_json(tmp_path) -> None:
    image = tmp_path / "front.png"
    image.write_bytes(b"image bytes")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["content-type"] == "application/json"
        assert request.headers["idempotency-key"] == "upload-1"
        assert json.loads(request.content) == {
            "file": base64.b64encode(b"image bytes").decode("ascii"),
            "filename": "front.png",
        }
        return httpx.Response(200, json={"ok": True, "data": {"id": "uploaded"}})

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await InfraiImages("test", client=client).upload(image, "upload-1")

    assert asyncio.run(run()) == "uploaded"
