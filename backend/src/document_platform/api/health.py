"""Health routes contain no database or messaging implementation details."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from document_platform.application.readiness import ReadinessService


def health_router(readiness: ReadinessService) -> APIRouter:
    """Build the minimal foundation endpoints, before document APIs are introduced."""
    router = APIRouter(prefix="/api/v1", tags=["health"])

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/ready")
    def ready() -> JSONResponse:
        checks = readiness.check()
        available = all(value == "ok" for value in checks.values())
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "checks": checks},
            status_code=200 if available else 503,
        )

    return router
