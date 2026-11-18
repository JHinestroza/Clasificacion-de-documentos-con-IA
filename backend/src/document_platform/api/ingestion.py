"""Thin authenticated HTTP contracts for intake. Rules and transactions live in use cases."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import APIKeyCookie
from pydantic import Field, StrictBool

from document_platform.api.identity import (
    SESSION_COOKIE,
    InputModel,
    csrf_token,
    invoke,
    no_cache,
    session_token,
)
from document_platform.application.identity.service import IdentityService
from document_platform.application.ingestion.service import IngestionService
from document_platform.config import Settings
from document_platform.domain.ingestion.models import Record


class FondsInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    storage_key: str = Field(min_length=1, max_length=64)


class ReasonInput(InputModel):
    reason: str = Field(min_length=3, max_length=500)


class GrantInput(ReasonInput):
    enabled: StrictBool


class BatchInput(InputModel):
    fonds_id: UUID


def ingestion_router(
    service: IngestionService, identity: IdentityService, settings: Settings
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/ingestion",
        tags=["ingestion"],
        dependencies=[
            Depends(no_cache),
            Depends(
                APIKeyCookie(name=SESSION_COOKIE, scheme_name="sessionCookie", auto_error=False)
            ),
        ],
    )

    def csrf(request: Request) -> str:
        return csrf_token(request, identity, settings)

    @router.get("/fonds")
    def fonds(request: Request) -> list[Record]:
        return invoke(lambda: service.fonds(session_token(request)))

    @router.post("/fonds", status_code=201)
    def create_fonds(body: FondsInput, request: Request) -> Record:
        value = csrf(request)
        return invoke(
            lambda: service.create_fonds(session_token(request), value, body.name, body.storage_key)
        )

    @router.get("/fonds/{fonds_id}/members")
    def members(fonds_id: UUID, request: Request) -> list[Record]:
        return invoke(lambda: service.members(session_token(request), fonds_id))

    @router.put("/fonds/{fonds_id}/members/{user_id}")
    def grant(fonds_id: UUID, user_id: UUID, body: GrantInput, request: Request) -> Record:
        value = csrf(request)
        return invoke(
            lambda: service.grant(
                session_token(request), value, fonds_id, user_id, body.enabled, body.reason
            )
        )

    @router.get("/fonds/{fonds_id}/batches")
    def batches(
        fonds_id: UUID,
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1000000),
    ) -> list[Record]:
        return invoke(lambda: service.batches(session_token(request), fonds_id, limit, offset))

    @router.post("/batches", status_code=201)
    def start(body: BatchInput, request: Request) -> Record:
        value = csrf(request)
        return invoke(lambda: service.start(session_token(request), value, body.fonds_id))

    @router.get("/batches/{batch_id}")
    def detail(batch_id: UUID, request: Request) -> Record:
        return invoke(lambda: service.detail(session_token(request), batch_id))

    @router.post("/batches/{batch_id}/{command}")
    def command(batch_id: UUID, command: str, body: ReasonInput, request: Request) -> Record:
        value = csrf(request)
        return invoke(
            lambda: service.command(session_token(request), value, batch_id, command, body.reason)
        )

    @router.get("/batches/{batch_id}/items")
    def items(
        batch_id: UUID,
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1000000),
        search: str = Query(default="", max_length=100),
        state: str = Query(default="", max_length=24),
    ) -> list[Record]:
        return invoke(
            lambda: service.items(session_token(request), batch_id, limit, offset, search, state)
        )

    @router.get("/batches/{batch_id}/events")
    def events(
        batch_id: UUID,
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=1000000),
    ) -> list[Record]:
        return invoke(lambda: service.events(session_token(request), batch_id, limit, offset))

    return router
