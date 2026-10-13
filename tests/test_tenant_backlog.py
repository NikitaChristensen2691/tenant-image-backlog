import asyncio
from pathlib import Path

import pytest

from saas_image_backlog.tenant_backlog import AccountInactive, AccountState, BacklogItem, TenantBacklog


class RecordingGateway:
    def __init__(self) -> None:
        self.uploads: list[Path] = []

    async def upload(self, path: Path, idempotency_key: str) -> str:
        self.uploads.append(path)
        return f"image-{path.stem}"

    async def smart_crop(self, image_id: str, aspect: str, idempotency_key: str) -> dict[str, str]:
        return {"id": f"crop-{image_id}", "aspect": aspect}


def test_suspended_tenant_cannot_drain_backlog() -> None:
    gateway = RecordingGateway()
    backlog = TenantBacklog(gateway)
    backlog.onboard("acme")
    backlog.set_state("acme", AccountState.SUSPENDED)

    with pytest.raises(AccountInactive):
        asyncio.run(backlog.process("acme", [BacklogItem(Path("catalog.png"), "1:1")]))

    assert gateway.uploads == []


def test_active_tenant_gets_ordered_results() -> None:
    gateway = RecordingGateway()
    backlog = TenantBacklog(gateway, concurrency=2)
    backlog.onboard("acme")

    result = asyncio.run(
        backlog.process(
            "acme",
            [BacklogItem(Path("first.png"), "1:1"), BacklogItem(Path("second.jpg"), "16:9")],
        )
    )

    assert [item.source for item in result] == ["first.png", "second.jpg"]
    assert result[1].output["aspect"] == "16:9"
