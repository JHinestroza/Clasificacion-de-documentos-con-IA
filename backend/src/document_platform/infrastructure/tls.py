"""TLS contexts that never disable certificate verification."""

import ssl
from typing import Any

from document_platform.config import Settings


def broker_ssl_options(settings: Settings) -> dict[str, Any]:
    """Configure py-amqp to verify the CA and the configured broker hostname."""
    # Validate the CA before a worker starts, rather than failing only on first use.
    ssl.create_default_context(cafile=str(settings.tls_ca_file))
    return {
        "ca_certs": str(settings.tls_ca_file),
        "cert_reqs": ssl.CERT_REQUIRED,
        "server_hostname": settings.broker_host,
        "ssl_version": ssl.PROTOCOL_TLS_CLIENT,
        "tls_minimum_version": ssl.TLSVersion.TLSv1_2,
    }


def api_ssl_context(settings: Settings) -> ssl.SSLContext:
    """Require an API certificate/key pair and permit TLS 1.2 or newer."""
    if settings.api_cert_file is None or settings.api_key_file is None:
        raise ValueError("API certificate and private-key files are required")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(str(settings.api_cert_file), str(settings.api_key_file))
    except (OSError, ssl.SSLError):
        raise ValueError("API certificate and private key are invalid or do not match") from None
    return context
