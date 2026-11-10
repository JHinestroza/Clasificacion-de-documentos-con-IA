"""Real loopback TLS tests exercise the same Uvicorn builder as the API entry point."""

import http.client
import socket
import ssl
import threading
import time
from collections.abc import Iterator

import pytest

from document_platform.__main__ import build_server
from document_platform.config import Settings


@pytest.fixture
def running_api(settings: Settings) -> Iterator[tuple[str, int, Settings]]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(16)
    listener.setblocking(False)
    port = int(listener.getsockname()[1])
    settings.api_port = port
    server = build_server(settings)
    worker = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started:
            if not worker.is_alive() or time.monotonic() > deadline:
                pytest.fail("HTTPS server did not start")
            time.sleep(0.01)
        yield "127.0.0.1", port, settings
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        listener.close()
        assert not worker.is_alive(), "HTTPS server did not shut down"


def test_real_https_health_with_trusted_ca(running_api: tuple[str, int, Settings]) -> None:
    host, port, settings = running_api
    context = ssl.create_default_context(cafile=str(settings.tls_ca_file))
    connection = http.client.HTTPSConnection(host, port, context=context, timeout=3)
    try:
        connection.request("GET", "/api/v1/health")
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b'{"status":"ok"}'
        assert response.getheader("Server") is None
    finally:
        connection.close()


def test_tls_rejects_an_untrusted_ca(running_api: tuple[str, int, Settings]) -> None:
    host, port, _settings = running_api
    # No trust anchors are installed in this client context.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    with (
        socket.create_connection((host, port), timeout=3) as raw,
        pytest.raises(ssl.SSLCertVerificationError),
    ):
        context.wrap_socket(raw, server_hostname="localhost")


def test_tls_rejects_hostname_mismatch(running_api: tuple[str, int, Settings]) -> None:
    host, port, settings = running_api
    context = ssl.create_default_context(cafile=str(settings.tls_ca_file))
    with (
        socket.create_connection((host, port), timeout=3) as raw,
        pytest.raises(ssl.SSLCertVerificationError, match="[Hh]ostname mismatch"),
    ):
        context.wrap_socket(raw, server_hostname="different-service.invalid")


def test_plaintext_http_cannot_reach_api(running_api: tuple[str, int, Settings]) -> None:
    host, port, _settings = running_api
    with socket.create_connection((host, port), timeout=3) as connection:
        connection.sendall(b"GET /api/v1/health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        try:
            response = connection.recv(4096)
        except (ConnectionResetError, TimeoutError):
            response = b""
    assert response == b""
