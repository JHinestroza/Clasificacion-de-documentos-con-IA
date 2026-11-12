"""Broker connectivity using TLS and restricted application credentials."""

from urllib.parse import quote

from kombu.connection import Connection
from pydantic import SecretStr

from document_platform.config import Settings
from document_platform.infrastructure.tls import broker_ssl_options


def broker_url(settings: Settings) -> SecretStr:
    """Build a redacted AMQPS URL, correctly encoding credentials and vhost."""
    host = settings.broker_host
    if ":" in host:
        host = f"[{host}]"
    user = quote(settings.broker_user, safe="")
    password = quote(settings.broker_password.get_secret_value(), safe="")
    vhost = quote(settings.broker_vhost, safe="")
    return SecretStr(f"amqps://{user}:{password}@{host}:{settings.broker_port}/{vhost}")


def broker_connection(settings: Settings) -> Connection:
    """Build the verified AMQPS connection used by checks and the isolated probe."""
    timeout = settings.dependency_timeout_seconds
    return Connection(  # type: ignore[no-untyped-call]
        hostname=settings.broker_host,
        port=settings.broker_port,
        userid=settings.broker_user,
        password=settings.broker_password.get_secret_value(),
        virtual_host=settings.broker_vhost,
        transport="pyamqp",
        ssl=broker_ssl_options(settings),
        connect_timeout=timeout,
        transport_options={
            "read_timeout": timeout,
            "write_timeout": timeout,
            "confirm_publish": True,
        },
    )


def check_broker(settings: Settings) -> None:
    """Authenticate and open a channel; do not declare queues or publish messages."""
    with broker_connection(settings) as connection:
        connection.connect()
        connection.channel().close()
