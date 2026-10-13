from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .infrai_images import InfraiError, InfraiImages, InfraiTransportError
from .tenant_backlog import AccountInactive, AccountState, BacklogItem, TenantBacklog, UnknownTenant


class TenantRequest(BaseModel):
    tenant_id: str = Field(min_length=1)


class StateRequest(BaseModel):
    state: AccountState


class ImageItemRequest(BaseModel):
    path: str = Field(min_length=1)
    aspect: str = Field(min_length=1)


class BatchRequest(BaseModel):
    tenant_id: str = Field(min_length=1)
    images: list[ImageItemRequest] = Field(min_length=1)


class StateResponse(BaseModel):
    tenant_id: str
    state: AccountState


class ImageResult(BaseModel):
    source: str
    output: dict[str, object]


class BatchResponse(BaseModel):
    tenant_id: str
    images: list[ImageResult]


def create_app(backlog: TenantBacklog | None = None) -> FastAPI:
    gateway: InfraiImages | None = None
    if backlog is None:
        api_key = os.environ.get("INFRAI_API_KEY")
        if not api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        gateway = InfraiImages(api_key)
        backlog = TenantBacklog(gateway)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if gateway is not None:
            await gateway.close()

    app = FastAPI(title="Tenant image backlog", lifespan=lifespan)

    @app.post("/tenants", response_model=StateResponse)
    async def onboard(request: TenantRequest) -> StateResponse:
        state = backlog.onboard(request.tenant_id)
        return StateResponse(tenant_id=request.tenant_id, state=state)

    @app.put("/admin/tenants/{tenant_id}/state", response_model=StateResponse)
    async def change_state(tenant_id: str, request: StateRequest) -> StateResponse:
        try:
            state = backlog.set_state(tenant_id, request.state)
        except UnknownTenant as exc:
            raise HTTPException(status_code=404, detail="Tenant not found") from exc
        return StateResponse(tenant_id=tenant_id, state=state)

    @app.post("/batches", response_model=BatchResponse)
    async def process_batch(request: BatchRequest) -> BatchResponse:
        items = [BacklogItem(path=Path(item.path), aspect=item.aspect) for item in request.images]
        try:
            completed = await backlog.process(request.tenant_id, items)
        except UnknownTenant as exc:
            raise HTTPException(status_code=404, detail="Tenant not found") from exc
        except AccountInactive as exc:
            raise HTTPException(status_code=409, detail="Tenant account is suspended") from exc
        except InfraiError as exc:
            status = exc.status_code if 400 <= exc.status_code < 500 else 502
            raise HTTPException(status_code=status, detail={"code": exc.code, "error": exc.detail}) from exc
        except InfraiTransportError as exc:
            raise HTTPException(status_code=502, detail="Image processing request did not complete") from exc
        return BatchResponse(
            tenant_id=request.tenant_id,
            images=[ImageResult(source=item.source, output=item.output) for item in completed],
        )

    return app


app = create_app()

