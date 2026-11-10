"""Workers cannot downgrade TLS or enable unsafe message formats."""

import ssl

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import broker_url
from document_platform.infrastructure.messaging.worker import create_celery


def test_worker_uses_verified_tls_without_api_private_key(settings: Settings) -> None:
    settings.api_cert_file = None
    settings.api_key_file = None
    app = create_celery(settings)
    assert app.conf.broker_use_ssl["cert_reqs"] == ssl.CERT_REQUIRED
    assert app.conf.broker_use_ssl["server_hostname"] == "rabbitmq"
    assert app.conf.broker_use_ssl["ssl_version"] == ssl.PROTOCOL_TLS_CLIENT
    assert "keyfile" not in app.conf.broker_use_ssl
    assert app.conf.accept_content == ["json"]
    assert app.conf.task_serializer == "json"
    assert app.conf.result_backend is None
    assert app.conf.task_ignore_result is True
    assert app.conf.worker_enable_remote_control is False
    assert app.conf.worker_send_task_events is False
    assert app.conf.task_create_missing_queues is False
    assert app.conf.task_default_queue == "document_platform.processing"
    assert app.conf.task_default_exchange == "document_platform.tasks"


def test_broker_url_encodes_credentials_and_has_redacted_repr(settings: Settings) -> None:
    assert broker_url(settings).get_secret_value().startswith("amqps://")
    assert settings.broker_password.get_secret_value() not in repr(broker_url(settings))
