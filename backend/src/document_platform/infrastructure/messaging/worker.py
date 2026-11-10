"""Create the worker application without coupling business logic to Celery."""

from celery import Celery
from kombu.entity import Exchange, Queue

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import broker_url
from document_platform.infrastructure.tls import broker_ssl_options


def create_celery(settings: Settings) -> Celery:
    """Configure an idle foundation worker; document tasks arrive in later features."""
    app = Celery("document_platform", broker=broker_url(settings).get_secret_value())
    # Kombu's entity constructors do not expose annotations to strict type checking.
    exchange = Exchange(  # type: ignore[no-untyped-call]
        settings.broker_task_exchange, type="direct", durable=True
    )
    app.conf.update(
        broker_use_ssl=broker_ssl_options(settings),
        broker_connection_timeout=settings.dependency_timeout_seconds,
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=10,
        broker_heartbeat=30,
        broker_transport_options={"confirm_publish": True},
        accept_content=["json"],
        task_serializer="json",
        result_serializer="json",
        result_accept_content=["json"],
        task_ignore_result=True,
        task_store_errors_even_if_ignored=False,
        task_default_queue=settings.broker_task_queue,
        task_default_exchange=settings.broker_task_exchange,
        task_default_exchange_type="direct",
        task_default_routing_key=settings.broker_task_queue,
        task_default_delivery_mode="persistent",
        task_create_missing_queues=False,
        task_queues=(
            Queue(  # type: ignore[no-untyped-call]
                settings.broker_task_queue,
                exchange=exchange,
                routing_key=settings.broker_task_queue,
                durable=True,
            ),
        ),
        worker_enable_remote_control=False,
        worker_send_task_events=False,
        task_send_sent_event=False,
        worker_hijack_root_logger=False,
        worker_log_color=False,
        worker_prefetch_multiplier=1,
        enable_utc=True,
        timezone="UTC",
    )
    return app
