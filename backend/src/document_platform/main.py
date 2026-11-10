"""Application factory; importing this module does not read secrets or connect."""

from fastapi import FastAPI

from document_platform.api.health import health_router
from document_platform.api.security import RequireHTTPS
from document_platform.application.readiness import ReadinessService
from document_platform.config import Settings
from document_platform.infrastructure.tls import api_ssl_context


def create_app(
    settings: Settings | None = None,
    readiness: ReadinessService | None = None,
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
    app.add_middleware(RequireHTTPS)
    app.include_router(health_router(readiness or ReadinessService.from_settings(settings)))
    return app
