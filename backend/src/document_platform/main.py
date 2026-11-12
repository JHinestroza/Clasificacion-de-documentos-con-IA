"""Application factory; importing this module does not read secrets or connect."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from document_platform.api.health import health_router
from document_platform.api.identity import CSRF_COOKIE, SESSION_COOKIE, identity_router
from document_platform.api.security import RequireHTTPS
from document_platform.application.identity.service import IdentityService
from document_platform.application.readiness import ReadinessService
from document_platform.config import Settings
from document_platform.domain.identity.models import IdentityError
from document_platform.identity_runtime import build_identity_service
from document_platform.infrastructure.tls import api_ssl_context


def create_app(
    settings: Settings | None = None,
    readiness: ReadinessService | None = None,
    identity: IdentityService | None = None,
) -> FastAPI:
    """Validate API TLS and build the ASGI app without contacting dependencies."""
    settings = settings or Settings()
    api_ssl_context(settings)
    app = FastAPI(
        title="Document platform",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        debug=False,
    )
    identity = identity or build_identity_service(settings)
    app.state.identity_service = identity

    @app.exception_handler(IdentityError)
    async def identity_error(request: Request, error: IdentityError) -> JSONResponse:
        response = JSONResponse(
            {"detail": str(error)}, status_code=error.status, headers={"Cache-Control": "no-store"}
        )
        if error.status == 401:
            for name in (SESSION_COOKIE, CSRF_COOKIE):
                response.delete_cookie(
                    name, path="/", secure=True, httponly=True, samesite="strict"
                )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        try:
            await run_in_threadpool(
                app.state.identity_service.audit_rejection, "security.validation"
            )
        except Exception:
            return JSONResponse(
                {"detail": "Identity service unavailable"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            {"detail": "Invalid request"}, status_code=422, headers={"Cache-Control": "no-store"}
        )

    app.include_router(identity_router(identity, settings))
    app.add_middleware(RequireHTTPS)
    app.include_router(health_router(readiness or ReadinessService.from_settings(settings)))
    return app
