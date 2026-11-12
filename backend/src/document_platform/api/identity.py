"""Thin HTTP adapters for identity; authorization and transactions live in the service."""

import re
import secrets
from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool

from document_platform.application.identity.service import IdentityService
from document_platform.config import Settings
from document_platform.domain.identity.models import IdentityError, PermissionDenied

SESSION_COOKIE = "__Host-session"
CSRF_COOKIE = "__Host-csrf"


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class LoginInput(InputModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(repr=False, exclude=True, min_length=1, max_length=128)


class UserInput(LoginInput):
    is_superuser: StrictBool = False


class PasswordInput(InputModel):
    current_password: SecretStr = Field(repr=False, exclude=True, min_length=1, max_length=128)
    new_password: SecretStr = Field(repr=False, exclude=True, min_length=16, max_length=128)


class ActiveInput(InputModel):
    active: StrictBool
    reason: str = Field(min_length=3, max_length=500)


class PermissionsInput(InputModel):
    permissions: set[str] = Field(max_length=20)
    reason: str = Field(min_length=3, max_length=500)


class UserView(BaseModel):
    id: UUID
    username: str
    is_active: bool
    is_superuser: bool
    permissions: list[str]
    created_at: datetime


class AuditView(BaseModel):
    id: UUID
    actor_id: UUID | None
    action: str
    resource_id: UUID | None
    outcome: str
    occurred_at: datetime
    reason: str | None


class LoginView(BaseModel):
    user: UserView
    csrf_token: str


class CsrfView(BaseModel):
    csrf_token: str


def invoke[T](operation: Callable[[], T]) -> T:
    """Never let transport/database exceptions escape into server tracebacks or responses."""
    try:
        return operation()
    except IdentityError:
        raise
    except Exception:
        raise HTTPException(
            503, "Identity service unavailable", headers={"Cache-Control": "no-store"}
        ) from None


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def identity_router(service: IdentityService, settings: Settings) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(no_cache)],
        tags=["identity"],
        responses={
            400: {"description": "Invalid operation or HTTPS required"},
            401: {"description": "Authentication required or invalid credentials"},
            403: {"description": "Permission or Origin/CSRF validation denied"},
            409: {"description": "Account conflict or last active superuser protection"},
            422: {"description": "Invalid request (values are not echoed)"},
            429: {"description": "Temporary login or hashing limit"},
            503: {"description": "Identity persistence unavailable"},
        },
    )

    # Publish the cookie contract in OpenAPI; the service still enforces authentication.
    authenticated = [
        Depends(APIKeyCookie(name=SESSION_COOKIE, scheme_name="sessionCookie", auto_error=False))
    ]

    def token(request: Request) -> str:
        return request.cookies.get(SESSION_COOKIE, "")

    def csrf(request: Request) -> str:
        supplied = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        if (
            request.headers.get("origin") not in settings.auth_allowed_origins
            or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", cookie) is None
            or not secrets.compare_digest(cookie.encode(), supplied.encode())
        ):
            invoke(lambda: service.audit_rejection("security.csrf"))
            raise PermissionDenied("Request security validation failed")
        return supplied

    @router.get("/auth/csrf", response_model=CsrfView)
    def get_csrf(request: Request, response: Response) -> dict[str, str]:
        value = (
            invoke(lambda: service.csrf(token(request)))
            if token(request)
            else secrets.token_urlsafe(32)
        )
        response.set_cookie(
            CSRF_COOKIE, value, secure=True, httponly=True, samesite="strict", path="/"
        )
        return {"csrf_token": value}

    @router.post("/auth/login", response_model=LoginView)
    def login(body: LoginInput, request: Request, response: Response) -> dict[str, object]:
        csrf(request)
        result = invoke(
            lambda: service.login(
                body.username, body.password.get_secret_value(), token(request) or None
            )
        )
        response.set_cookie(
            SESSION_COOKIE,
            result.token,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
            max_age=settings.auth_absolute_seconds,
        )
        response.set_cookie(
            CSRF_COOKIE, result.csrf_token, secure=True, httponly=True, samesite="strict", path="/"
        )
        return {"user": result.user.public(), "csrf_token": result.csrf_token}

    @router.get("/auth/me", response_model=UserView, dependencies=authenticated)
    def me(request: Request) -> dict[str, object]:
        return invoke(lambda: service.me(token(request))).public()

    @router.post("/auth/logout", dependencies=authenticated)
    def logout(request: Request, response: Response) -> dict[str, str]:
        value = csrf(request)
        invoke(lambda: service.logout(token(request), value))
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")
        return {"status": "signed_out"}

    @router.post("/auth/password", dependencies=authenticated)
    def change_password(
        body: PasswordInput, request: Request, response: Response
    ) -> dict[str, str]:
        value = csrf(request)
        invoke(
            lambda: service.change_password(
                token(request),
                value,
                body.current_password.get_secret_value(),
                body.new_password.get_secret_value(),
            )
        )
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")
        return {"status": "password_changed_sessions_revoked"}

    @router.get("/users", response_model=list[UserView], dependencies=authenticated)
    def users(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ) -> list[dict[str, object]]:
        return [
            user.public()
            for user in invoke(lambda: service.list_users(token(request), limit, offset))
        ]

    @router.post("/users", status_code=201, response_model=UserView, dependencies=authenticated)
    def create_user(body: UserInput, request: Request) -> dict[str, object]:
        value = csrf(request)
        return invoke(
            lambda: service.create_user(
                token(request),
                value,
                body.username,
                body.password.get_secret_value(),
                body.is_superuser,
            )
        ).public()

    @router.patch("/users/{user_id}/active", response_model=UserView, dependencies=authenticated)
    def active(user_id: UUID, body: ActiveInput, request: Request) -> dict[str, object]:
        value = csrf(request)
        return invoke(
            lambda: service.set_active(token(request), value, user_id, body.active, body.reason)
        ).public()

    @router.put("/users/{user_id}/permissions", response_model=UserView, dependencies=authenticated)
    def permissions(user_id: UUID, body: PermissionsInput, request: Request) -> dict[str, object]:
        value = csrf(request)
        return invoke(
            lambda: service.set_permissions(
                token(request), value, user_id, frozenset(body.permissions), body.reason
            )
        ).public()

    @router.get("/permissions", dependencies=authenticated)
    def catalog(request: Request) -> list[str]:
        return invoke(lambda: service.permission_catalog(token(request)))

    @router.get("/audit", response_model=list[AuditView], dependencies=authenticated)
    def audit(
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ) -> list[dict[str, object]]:
        return [
            entry.public()
            for entry in invoke(lambda: service.list_audit(token(request), limit, offset))
        ]

    return router
