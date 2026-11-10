"""Reject unencrypted HTTP even if the ASGI app is started incorrectly."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequireHTTPS:
    """Permit HTTP requests only when the server reports a TLS connection."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("scheme") != "https":
            response = JSONResponse({"detail": "HTTPS required"}, status_code=400)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
