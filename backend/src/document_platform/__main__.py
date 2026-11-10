"""Start the API with HTTPS; no plaintext listener or trusted proxy headers."""

import logging

import uvicorn

from document_platform.config import Settings
from document_platform.infrastructure.tls import api_ssl_context
from document_platform.main import create_app


def build_server(settings: Settings) -> uvicorn.Server:
    """Build the production entry point with TLS and loopback binding by default."""
    context = api_ssl_context(settings)
    config = uvicorn.Config(
        create_app(settings),
        host=settings.api_host,
        port=settings.api_port,
        ssl_context_factory=lambda _config, _default_factory: context,
        proxy_headers=False,
        server_header=False,
        access_log=False,
        log_level=settings.log_level.lower(),
    )
    return uvicorn.Server(config)


def main() -> None:
    """Fail closed on missing configuration and start the single API process."""
    try:
        settings = Settings()
        server = build_server(settings)
    except (ValueError, OSError):
        raise SystemExit("Invalid startup configuration; check secret and TLS files.") from None
    logging.basicConfig(level=settings.log_level)
    server.run()


if __name__ == "__main__":
    main()
