"""A bounded JSON probe on a dedicated queue, independent of document processing."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from kombu.entity import Exchange, Queue
from kombu.exceptions import ChannelError
from kombu.messaging import Producer

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import broker_connection

PROBE_NAME = "document_platform.integration"


def probe_queue(channel: Any) -> Any:
    """Use only the dedicated probe topology; never purge or consume other queues."""
    exchange = Exchange(PROBE_NAME, type="direct", durable=True)  # type: ignore[no-untyped-call]
    return Queue(  # type: ignore[no-untyped-call]
        PROBE_NAME,
        exchange=exchange,
        routing_key=PROBE_NAME,
        durable=True,
    )(channel)


def validate_event(payload: Any, message_id: str | None) -> str:
    """Reject anything except this tool's small synthetic event before acknowledging."""
    if not isinstance(payload, dict) or set(payload) != {
        "event_id",
        "event_type",
        "schema_version",
        "timestamp",
    }:
        raise ValueError("Unexpected probe payload; message was requeued")
    if payload["event_type"] != "integration.ping" or type(payload["schema_version"]) is not int:
        raise ValueError("Unexpected probe event; message was requeued")
    if payload["schema_version"] != 1 or not isinstance(payload["event_id"], str):
        raise ValueError("Unsupported probe event; message was requeued")
    event_id = str(UUID(payload["event_id"]))
    if event_id != message_id or not isinstance(payload["timestamp"], str):
        raise ValueError("Probe identity is inconsistent; message was requeued")
    timestamp = datetime.fromisoformat(payload["timestamp"])
    if timestamp.utcoffset() is None:
        raise ValueError("Probe timestamp has no timezone; message was requeued")
    return event_id


def publish_probe(settings: Settings, count: int = 1) -> dict[str, Any]:
    """Publish persistent synthetic messages with confirms, leaving them in the queue."""
    if not 1 <= count <= 100:
        raise ValueError("Count must be between 1 and 100")
    identifiers: list[str] = []
    with broker_connection(settings) as connection:
        connection.connect()
        with connection.channel() as channel:
            queue = probe_queue(channel)
            queue.declare()
            producer = Producer(channel)  # type: ignore[no-untyped-call]
            for _ in range(count):
                event_id = str(uuid4())
                producer.publish(  # type: ignore[no-untyped-call]
                    {
                        "event_id": event_id,
                        "event_type": "integration.ping",
                        "schema_version": 1,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    exchange=queue.exchange,
                    routing_key=PROBE_NAME,
                    serializer="json",
                    delivery_mode=2,
                    message_id=event_id,
                    correlation_id=event_id,
                    retry=False,
                    mandatory=True,
                )
                identifiers.append(event_id)
    return {"queue": PROBE_NAME, "published_confirmed": len(identifiers), "event_ids": identifiers}


def queue_status(settings: Settings) -> dict[str, Any]:
    """Read server counts without declaring a missing queue or removing messages."""
    with broker_connection(settings) as connection:
        connection.connect()
        try:
            with connection.channel() as channel:
                result = channel.queue_declare(queue=PROBE_NAME, passive=True)
        except ChannelError as exc:
            if getattr(exc, "reply_code", None) != 404:
                raise
            return {"queue": PROBE_NAME, "exists": False, "messages_ready": 0, "consumers": 0}
    return {
        "queue": PROBE_NAME,
        "exists": True,
        "messages_ready": result.message_count,
        "consumers": result.consumer_count,
    }


def consume_probe(settings: Settings, limit: int = 1, *, requeue: bool = False) -> dict[str, Any]:
    """Acknowledge validated probes, or deliberately requeue one to demonstrate recovery."""
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    identifiers: list[str] = []
    redelivered = 0
    with broker_connection(settings) as connection:
        connection.connect()
        with connection.channel() as channel:
            queue = probe_queue(channel)
            # A missing queue is an error here; consumption never creates one implicitly.
            channel.queue_declare(queue=PROBE_NAME, passive=True)
            for _ in range(limit):
                message = queue.get(no_ack=False, accept=["json"])
                if message is None:
                    break
                try:
                    event_id = validate_event(message.payload, message.properties.get("message_id"))
                except Exception:
                    message.reject(requeue=True)
                    raise ValueError("Unrecognized probe message; retained in the queue") from None
                redelivered += bool(message.delivery_info.get("redelivered", False))
                if requeue:
                    message.reject(requeue=True)
                else:
                    message.ack()
                identifiers.append(event_id)
                if requeue:
                    break
    return {
        "queue": PROBE_NAME,
        "acknowledged": 0 if requeue else len(identifiers),
        "requeued": len(identifiers) if requeue else 0,
        "redelivered": redelivered,
        "event_ids": identifiers,
    }
