"""Celery protocol-v2 producer with verified AMQPS, confirms and returned-message detection."""

from typing import Any

from kombu.entity import Exchange, Queue
from kombu.messaging import Producer

from document_platform.config import Settings
from document_platform.domain.ingestion.models import Record
from document_platform.infrastructure.messaging.connection import broker_connection
from document_platform.infrastructure.messaging.worker import create_celery

TASK = "document_platform.process_document.v1"
TEST_QUEUE = "document_platform.ingestion_test"


def intake_queue(settings: Settings) -> str:
    """A synthetic database can never address the operational queue."""
    if (
        settings.broker_task_exchange != "document_platform.tasks"
        or settings.broker_task_queue != "document_platform.processing"
    ):
        raise ValueError("Unapproved intake topology")
    return (
        TEST_QUEUE
        if settings.db_name.startswith("document_platform_test_")
        else settings.broker_task_queue
    )


def publish_intake(settings: Settings, event: Record) -> None:
    queue_name = intake_queue(settings)
    app = create_celery(settings)
    returned = []

    def on_return(*args: Any, **kwargs: Any) -> None:
        returned.append(True)

    try:
        with broker_connection(settings) as connection:
            connection.connect()
            with connection.channel() as channel:
                exchange = Exchange(settings.broker_task_exchange, type="direct", durable=True)  # type: ignore[no-untyped-call]
                queue = Queue(queue_name, exchange=exchange, routing_key=queue_name, durable=True)  # type: ignore[no-untyped-call]
                queue(channel).declare()  # type: ignore[no-untyped-call]
                producer = Producer(channel, on_return=on_return)  # type: ignore[no-untyped-call]
                message = app.amqp.create_task_message(
                    str(event["id"]),
                    TASK,
                    args=(),
                    kwargs=event["payload"],
                    ignore_result=True,
                    origin="document-platform",
                )
                app.amqp.send_task_message(
                    producer,
                    TASK,
                    message,
                    exchange=exchange,
                    routing_key=queue_name,
                    queue=queue,
                    declare=[queue],
                    mandatory=True,
                    retry=False,
                    delivery_mode=2,
                    serializer="json",
                )
                if returned:
                    raise ConnectionError("Task had no route")
    finally:
        app.close()
