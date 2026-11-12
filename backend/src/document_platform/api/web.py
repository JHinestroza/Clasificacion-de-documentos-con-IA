"""Serve only the compiled public React shell and fingerprinted assets, over existing HTTPS."""

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from document_platform.config import Settings

ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}-[A-Za-z0-9_-]{6,}\.(?:js|css|svg|woff2)")
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; worker-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class WebSecurityHeaders:
    """Apply browser protections to the shell, assets and API, including errors."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def secured(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.update(SECURITY_HEADERS)
                if "cache-control" not in headers:
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, secured)


class PublicAssets(StaticFiles):
    """Allow only fingerprinted build artifacts; never source maps or arbitrary files."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if ASSET_NAME.fullmatch(path) is None:
            raise HTTPException(404, "Not found")
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def attach_web(app: FastAPI, settings: Settings) -> None:
    """A missing build affects the web shell only; health/API remain independently usable."""
    directory = Path(settings.web_dist_dir)
    index = directory / "index.html"
    assets = directory / "assets"
    if (
        directory.is_dir()
        and not directory.is_symlink()
        and assets.is_dir()
        and not assets.is_symlink()
    ):
        app.mount(
            "/assets", PublicAssets(directory=assets, follow_symlink=False), name="web-assets"
        )

    @app.get("/", include_in_schema=False, response_model=None)
    def web_index() -> FileResponse | JSONResponse:
        if directory.is_symlink() or index.is_symlink() or not index.is_file():
            return JSONResponse(
                {"detail": "La interfaz no está disponible en este momento."}, status_code=503
            )
        return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-store"})
