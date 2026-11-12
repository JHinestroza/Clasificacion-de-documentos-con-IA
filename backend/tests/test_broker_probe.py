"""Dedicated queue probes validate before ACK and never touch document queues."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from document_platform.config import Settings
from document_platform.infrastructure.messaging.probe import (
    PROBE_NAME,
    consume_probe,
    publish_probe,
    queue_status,
    validate_event,
)


def event() -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": "integration.ping",
        "schema_version": 1,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@pytest.mark.parametrize(
    "change",
    [
        {"event_type": "documents.received"},
        {"schema_version": True},
        {"schema_version": 2},
        {"event_id": "invalid"},
        {"timestamp": "2026-11-12T12:00:00"},
        {"document_text": "must-not-be-accepted"},
    ],
)
def test_unknown_or_inconsistent_messages_are_not_accepted(change: dict) -> None:
    payload = event() | change
    with pytest.raises((ValueError, TypeError)):
        validate_event(payload, payload["event_id"])


def test_message_identity_must_match_properties() -> None:
    with pytest.raises(ValueError):
        validate_event(event(), str(uuid4()))


def test_publication_is_persistent_confirmed_and_namespaced(settings: Settings) -> None:
    connection = MagicMock()
    channel = connection.__enter__.return_value.channel.return_value.__enter__.return_value
    queue = MagicMock()
    with (
        patch(
            "document_platform.infrastructure.messaging.probe.broker_connection",
            return_value=connection,
        ),
        patch("document_platform.infrastructure.messaging.probe.probe_queue", return_value=queue),
        patch("document_platform.infrastructure.messaging.probe.Producer") as producer,
    ):
        result = publish_probe(settings, 2)
    assert result["published_confirmed"] == 2 and len(set(result["event_ids"])) == 2
    assert producer.call_args.args == (channel,)
    for call in producer.return_value.publish.call_args_list:
        assert call.kwargs["delivery_mode"] == 2
        assert call.kwargs["mandatory"] is True
        assert call.kwargs["routing_key"] == PROBE_NAME
        assert call.kwargs["serializer"] == "json"
    queue.declare.assert_called_once()


@pytest.mark.parametrize("count", [0, 101])
def test_unbounded_publication_is_rejected(settings: Settings, count: int) -> None:
    with pytest.raises(ValueError):
        publish_probe(settings, count)


def test_status_is_passive(settings: Settings) -> None:
    connection = MagicMock()
    channel = connection.__enter__.return_value.channel.return_value.__enter__.return_value
    channel.queue_declare.return_value = SimpleNamespace(message_count=3, consumer_count=0)
    with patch(
        "document_platform.infrastructure.messaging.probe.broker_connection",
        return_value=connection,
    ):
        assert queue_status(settings)["messages_ready"] == 3
    channel.queue_declare.assert_called_once_with(queue=PROBE_NAME, passive=True)


@pytest.mark.parametrize("requeue", [False, True])
def test_ack_or_requeue_are_explicit(settings: Settings, requeue: bool) -> None:
    payload = event()
    message = MagicMock(
        payload=payload,
        properties={"message_id": payload["event_id"]},
        delivery_info={"redelivered": True},
    )
    queue = MagicMock()
    queue.get.side_effect = [message, None]
    with (
        patch("document_platform.infrastructure.messaging.probe.broker_connection"),
        patch("document_platform.infrastructure.messaging.probe.probe_queue", return_value=queue),
    ):
        result = consume_probe(settings, 2, requeue=requeue)
    assert result["redelivered"] == 1
    if requeue:
        message.reject.assert_called_once_with(requeue=True)
        message.ack.assert_not_called()
    else:
        message.ack.assert_called_once()
        message.reject.assert_not_called()


def test_invalid_message_is_retained_without_ack(settings: Settings) -> None:
    message = MagicMock(payload={"document_text": "unexpected"})
    queue = MagicMock()
    queue.get.return_value = message
    with (
        patch("document_platform.infrastructure.messaging.probe.broker_connection"),
        patch("document_platform.infrastructure.messaging.probe.probe_queue", return_value=queue),
        pytest.raises(ValueError, match="retained"),
    ):
        consume_probe(settings)
    message.reject.assert_called_once_with(requeue=True)
    message.ack.assert_not_called()
