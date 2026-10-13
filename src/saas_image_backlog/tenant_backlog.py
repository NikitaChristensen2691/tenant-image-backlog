from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


class AccountState(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class AccountInactive(Exception):
    pass


class UnknownTenant(Exception):
    pass


class ImageGateway(Protocol):
    async def upload(self, path: Path, idempotency_key: str) -> str:
        raise AssertionError("protocol method")

    async def smart_crop(self, image_id: str, aspect: str, idempotency_key: str) -> dict[str, Any]:
        raise AssertionError("protocol method")


@dataclass(frozen=True)
class BacklogItem:
    path: Path
    aspect: str


@dataclass(frozen=True)
class CompletedImage:
    source: str
    output: dict[str, Any]


class TenantBacklog:
    def __init__(self, gateway: ImageGateway, concurrency: int = 4) -> None:
        self._gateway = gateway
        self._states: dict[str, AccountState] = {}
        self._slots = asyncio.Semaphore(concurrency)

    def onboard(self, tenant_id: str) -> AccountState:
        self._states.setdefault(tenant_id, AccountState.ACTIVE)
        return self._states[tenant_id]

    def set_state(self, tenant_id: str, state: AccountState) -> AccountState:
        if tenant_id not in self._states:
            raise UnknownTenant(tenant_id)
        self._states[tenant_id] = state
        return state

    def state(self, tenant_id: str) -> AccountState:
        try:
            return self._states[tenant_id]
        except KeyError as exc:
            raise UnknownTenant(tenant_id) from exc

    async def process(self, tenant_id: str, items: list[BacklogItem]) -> list[CompletedImage]:
        if self.state(tenant_id) is not AccountState.ACTIVE:
            raise AccountInactive(tenant_id)
        batch_id = uuid4().hex

        async def run(index: int, item: BacklogItem) -> CompletedImage:
            async with self._slots:
                uploaded = await self._gateway.upload(item.path, f"{batch_id}:upload:{index}")
                output = await self._gateway.smart_crop(
                    uploaded,
                    item.aspect,
                    f"{batch_id}:crop:{index}",
                )
                return CompletedImage(source=str(item.path), output=output)

        return list(await asyncio.gather(*(run(index, item) for index, item in enumerate(items))))
