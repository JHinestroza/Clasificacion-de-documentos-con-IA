"""Real isolated PostgreSQL intake state, recovery, least privilege and HTTP scope."""

import os
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from document_platform.domain.identity.models import PermissionDenied
from document_platform.infrastructure.persistence.database import connect_database
from document_platform.infrastructure.persistence.ingestion import IngestionUnitOfWork
from document_platform.infrastructure.storage.intake import IntakeStorage
from document_platform.ingestion_runtime import build_ingestion_service, build_runner
from document_platform.main import create_app

from .conftest import TEST_PASSWORD, new_environment


@pytest.fixture
def intake_env(tmp_path):
    if os.environ.get("RUN_PG_INTEGRATION") != "1":
        pytest.skip("Set RUN_PG_INTEGRATION=1 for isolated real PostgreSQL intake checks")
    settings, identity, admin = new_environment()
    settings = settings.model_copy(update={"storage_root": tmp_path / "documents"})
    service = build_ingestion_service(settings, identity)
    login = identity.login(admin.username, TEST_PASSWORD)
    fonds = service.create_fonds(login.token, login.csrf_token, "UFM", "UFM")
    storage = IntakeStorage(settings.storage_root)
    published = []
    runner = build_runner(settings)
    runner.publish = lambda event: published.append(event)
    return settings, identity, service, login, fonds, storage, runner, published


def put(storage, code="CAB01", valid=True):
    path = storage.path("UFM/incoming/" + code + ".pdf")
    if valid:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with path.open("wb") as stream:
            writer.write(stream)
    else:
        path.write_bytes(b"invalid synthetic PDF")
    return path


def drain(runner):
    for _ in range(30):
        if not runner.step():
            return
    raise AssertionError("Synthetic intake did not become idle")


def start(env):
    _, _, service, login, fonds, _, _, _ = env
    return service.start(login.token, login.csrf_token, fonds["id"])


def rows(env, batch):
    return env[2].items(env[3].token, batch["id"], 100, 0, "", "")


def test_valid_documents_confirm_and_duplicate_delivery_is_skipped(intake_env):
    env = intake_env
    settings, _, service, login, fonds, storage, runner, published = env
    original = put(storage).read_bytes()
    put(storage, "CAB02")
    batch = start(env)
    drain(runner)
    assert {r["job_state"] for r in rows(env, batch)} == {"queued"}
    assert len(published) == 2
    assert list((storage.root / "UFM/success").iterdir()) == []
    assert all(p.read_bytes() == original for p in (storage.root / "UFM/processing").iterdir())
    assert service.detail(login.token, batch["id"])["state"] == "completed"
    put(storage, "cab01")
    duplicate = start(env)
    drain(runner)
    assert rows(env, duplicate)[0]["state"] == "skipped"
    assert len(published) == 2 and len(list((storage.root / "UFM/skipped").iterdir())) == 1
    with connect_database(settings) as connection:
        assert (
            connection.execute("SELECT count(*) AS n FROM ingestion.documents").fetchone()["n"] == 2
        )
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM ingestion.events WHERE reason='same_content'"
            ).fetchone()["n"]
            == 1
        )


def test_invalid_pdf_preserves_content_with_failure_history(intake_env):
    env = intake_env
    storage, runner = env[5:7]
    data = put(storage, valid=False).read_bytes()
    batch = start(env)
    drain(runner)
    row = rows(env, batch)[0]
    assert row["state"] == "failed" and row["reason"] == "invalid_pdf"
    assert row["code"] == "CAB01" and row["size_bytes"] == len(data)
    assert row["sha256"] is not None
    assert next((storage.root / "UFM/failed").iterdir()).read_bytes() == data
    assert not env[7]
    assert any(
        e["action"] == "intake.failed" for e in env[2].events(env[3].token, batch["id"], 100, 0)
    )


def test_snapshot_pause_stop_and_next_batch_preserve_pending(intake_env):
    env = intake_env
    service, login, storage, runner = env[2], env[3], env[5], env[6]
    put(storage)
    put(storage, "CAB02")
    batch = start(env)
    service.command(login.token, login.csrf_token, batch["id"], "pause", "Synthetic pause")
    drain(runner)
    assert service.detail(login.token, batch["id"])["state"] == "paused"
    assert len(list((storage.root / "UFM/incoming").iterdir())) == 2
    service.command(login.token, login.csrf_token, batch["id"], "stop", "Synthetic stop")
    drain(runner)
    assert service.detail(login.token, batch["id"])["state"] == "stopped"
    new = start(env)
    put(storage, "CAB03")
    drain(runner)
    assert len(rows(env, new)) == 2
    assert storage.path("UFM/incoming/CAB03.pdf").exists()


def test_pause_finishes_current_admission_and_resume_continues(intake_env):
    env = intake_env
    service, login, runner = env[2], env[3], env[6]
    put(env[5])
    put(env[5], "CAB02")
    batch = start(env)
    original = runner.validate

    def paused(relative):
        service.command(
            login.token, login.csrf_token, batch["id"], "pause", "Pause during validation"
        )
        return original(relative)

    runner.validate = paused
    runner.step()
    runner.step()
    drain(runner)
    detail = service.detail(login.token, batch["id"])
    assert detail["state"] == "paused" and detail["counts"] == {"pending": 1, "queued": 1}
    runner.validate = original
    service.command(login.token, login.csrf_token, batch["id"], "resume", "Resume synthetic batch")
    drain(runner)
    assert service.detail(login.token, batch["id"])["counts"] == {"queued": 2}


def test_restarts_after_move_and_after_publish_keep_identity(intake_env):
    env = intake_env
    storage, runner = env[5:7]
    put(storage)
    batch = start(env)
    complete = storage.complete_move

    class InterruptedStorage(IntakeStorage):
        def complete_move(self, *args):
            complete(*args)
            raise KeyboardInterrupt("synthetic process crash after rename")

    runner.storage = InterruptedStorage(storage.root)
    with pytest.raises(KeyboardInterrupt):
        runner.step()
    runner.storage = storage
    seen = []

    def crash_after_publish(event):
        seen.append(str(event["id"]))
        raise KeyboardInterrupt("synthetic process crash after confirm")

    runner.publish = crash_after_publish
    with pytest.raises(KeyboardInterrupt):
        runner.step()
    with connect_database(env[0]) as connection:
        connection.execute(
            "UPDATE ingestion.outbox SET lease_until=now()-interval '1 "
            "second' WHERE state='sending'"
        )
    runner.publish = lambda event: seen.append(str(event["id"]))
    drain(runner)
    assert len(seen) == 2 and seen[0] == seen[1]
    assert rows(env, batch)[0]["job_state"] == "queued"
    with connect_database(env[0]) as connection:
        assert (
            connection.execute("SELECT count(*) AS n FROM ingestion.documents").fetchone()["n"] == 1
        )
        assert connection.execute("SELECT count(*) AS n FROM ingestion.jobs").fetchone()["n"] == 1


def test_broker_failure_stays_pending_and_authorized_retry_unblocks(intake_env):
    env = intake_env
    put(env[5])
    batch = start(env)
    runner = env[6]

    def unavailable(event):
        raise ConnectionError("synthetic private diagnostic")

    runner.publish = unavailable
    drain(runner)
    assert rows(env, batch)[0]["job_state"] == "pending_publish"
    with connect_database(env[0]) as connection:
        connection.execute(
            "UPDATE ingestion.outbox SET attempts=9,next_at=now()-interval '1 second'"
        )
    runner.step()
    assert env[2].detail(env[3].token, batch["id"])["blocked_publications"] == 1
    env[2].command(
        env[3].token, env[3].csrf_token, batch["id"], "retry-publication", "Broker recovered"
    )
    runner.publish = lambda event: env[7].append(event)
    drain(runner)
    assert rows(env, batch)[0]["job_state"] == "queued" and len(env[7]) == 1


def test_scope_action_and_revocation_apply_to_queries_commands_and_audit(intake_env):
    env = intake_env
    settings, identity, service, admin, fonds, storage, runner, _ = env
    user = identity.create_user(
        admin.token, admin.csrf_token, "operator_" + uuid4().hex[:8], TEST_PASSWORD
    )
    identity.set_permissions(
        admin.token,
        admin.csrf_token,
        user.id,
        frozenset({"documents.read", "processing.start", "audit.read"}),
        "Synthetic permissions",
    )
    login = identity.login(user.username, TEST_PASSWORD)
    put(storage)
    with pytest.raises(PermissionDenied):
        service.start(login.token, login.csrf_token, fonds["id"])
    service.grant(
        admin.token, admin.csrf_token, fonds["id"], user.id, True, "Synthetic fonds access"
    )
    batch = service.start(login.token, login.csrf_token, fonds["id"])
    service.grant(
        admin.token, admin.csrf_token, fonds["id"], user.id, False, "Synthetic revocation"
    )
    drain(runner)
    assert service.detail(admin.token, batch["id"])["state"] == "paused"
    for operation in [
        lambda: service.detail(login.token, batch["id"]),
        lambda: service.items(login.token, batch["id"], 20, 0, "", ""),
        lambda: service.events(login.token, batch["id"], 20, 0),
    ]:
        with pytest.raises(PermissionDenied):
            operation()
    assert all(a.fonds_id is None for a in identity.list_audit(login.token, 100, 0))
    assert storage.path("UFM/incoming/CAB01.pdf").exists()
    service.command(admin.token, admin.csrf_token, batch["id"], "resume", "Superuser takes over")
    drain(runner)
    assert rows(env, batch)[0]["job_state"] == "queued"


def test_http_csrf_and_fonds_scope_are_enforced(intake_env):
    env = intake_env
    settings, identity, _, _, fonds, *_ = env
    with TestClient(
        create_app(settings, identity=identity), base_url="https://localhost:8443"
    ) as client:
        assert client.get("/api/v1/ingestion/fonds").status_code == 401
        security = client.app.openapi()["paths"]["/api/v1/ingestion/fonds"]["get"]["security"]
        assert security == [{"sessionCookie": []}]
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"username": "test_admin", "password": TEST_PASSWORD},
                headers={"Origin": "https://localhost:8443", "X-CSRF-Token": csrf},
            ).status_code
            == 200
        )
        assert client.get("/api/v1/ingestion/fonds").json()[0]["storage_key"] == "UFM"
        assert (
            client.post(
                "/api/v1/ingestion/batches", json={"fonds_id": str(fonds["id"])}
            ).status_code
            == 403
        )
        assert client.get("/api/v1/ingestion/batches/" + str(uuid4())).status_code == 403
        assert (
            client.get(
                "/api/v1/ingestion/fonds/" + str(fonds["id"]) + "/batches?offset=-1"
            ).status_code
            == 422
        )


def test_history_is_insert_only_and_runtime_cannot_create_tables(intake_env):
    import psycopg

    with connect_database(intake_env[0]) as connection:
        for statement in [
            "UPDATE ingestion.events SET reason=NULL",
            "DELETE FROM ingestion.events",
            "TRUNCATE ingestion.events",
            "CREATE TABLE ingestion.forbidden(id int)",
            "DELETE FROM ingestion.documents",
            "UPDATE ingestion.documents SET code=code",
            "UPDATE ingestion.fonds SET storage_key=storage_key",
        ]:
            with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
                connection.execute(statement)


def test_failed_reader_cannot_bypass_filter_or_read_history(intake_env):
    env = intake_env
    settings, identity, service, admin, fonds, storage, runner, _ = env
    put(storage)
    put(storage, "CAB02", valid=False)
    batch = start(env)
    drain(runner)
    user = identity.create_user(
        admin.token, admin.csrf_token, "failed_" + uuid4().hex[:8], TEST_PASSWORD
    )
    identity.set_permissions(
        admin.token, admin.csrf_token, user.id, frozenset({"failed.read"}), "Synthetic limited role"
    )
    service.grant(admin.token, admin.csrf_token, fonds["id"], user.id, True, "Limited fonds access")
    login = identity.login(user.username, TEST_PASSWORD)
    limited = service.items(login.token, batch["id"], 20, 0, "", "queued")
    assert (
        len(limited) == 1
        and limited[0]["state"] == "failed"
        and limited[0]["original_name"] == "CAB02.pdf"
    )
    with pytest.raises(PermissionDenied):
        service.events(login.token, batch["id"], 20, 0)
    with connect_database(settings) as connection:
        audit = connection.execute(
            "SELECT * FROM identity.audit_logs WHERE action='fonds.grant'"
            " ORDER BY occurred_at DESC LIMIT 1"
        ).fetchone()
    assert (
        audit["actor_id"] == admin.user.id
        and audit["resource_id"] == user.id
        and audit["fonds_id"] == fonds["id"]
    )


def test_changed_input_and_second_process_are_safe(intake_env):
    env = intake_env
    storage, runner = env[5:7]
    path = put(storage)
    batch = start(env)
    with path.open("ab") as stream:
        stream.write(b"changed after snapshot")
    uow = IngestionUnitOfWork(env[0])
    with uow.runner_lock() as acquired:
        assert acquired and runner.step() is False
    drain(runner)
    assert rows(env, batch)[0]["reason"] == "changed"
    assert path.exists() and not env[7]


@pytest.mark.skipif(
    os.environ.get("RUN_RABBIT_INGESTION") != "1",
    reason="Requires approved local intake broker permissions",
)
def test_real_amqps_celery_envelope_and_owned_ack(intake_env):
    from kombu.entity import Queue

    from document_platform.infrastructure.messaging.connection import broker_connection
    from document_platform.infrastructure.messaging.intake import TASK, TEST_QUEUE, publish_intake

    env = intake_env
    runner = env[6]
    owned = set()

    def publish(event):
        publish_intake(env[0], event)
        owned.add(str(event["id"]))

    runner.publish = publish
    put(env[5])
    put(env[5], "CAB02")
    batch = start(env)
    drain(runner)
    assert len(owned) == 2 and all(r["job_state"] == "queued" for r in rows(env, batch))
    found = set()
    with broker_connection(env[0]) as connection, connection.channel() as channel:
        queue = Queue(TEST_QUEUE)(channel)
        # Unknown synthetic deliveries stay unacked and are returned on channel close.
        for _ in range(50):
            message = queue.get(no_ack=False, accept=["json"])
            if message is None:
                break
            event_id = message.properties.get("correlation_id")
            if event_id not in owned:
                continue
            assert message.headers["task"] == TASK
            assert message.properties["delivery_mode"] == 2
            assert message.payload[0] == []
            assert message.payload[1]["event_id"] == event_id
            assert set(message.payload[1]) == {
                "version",
                "event_id",
                "document_id",
                "job_id",
                "batch_id",
                "fonds_id",
                "correlation_id",
            }
            assert message.payload[1]["batch_id"] == str(batch["id"])
            message.ack()
            found.add(event_id)
            if found == owned:
                break
    assert found == owned


@pytest.mark.skipif(
    os.environ.get("RUN_RABBIT_INGESTION") != "1",
    reason="Requires approved local intake broker permissions",
)
def test_real_mandatory_publication_rejects_an_unroutable_message(intake_env, monkeypatch):
    from document_platform.infrastructure.messaging import intake as messaging

    factory = messaging.create_celery

    def make_app(settings):
        app = factory(settings)
        send = app.amqp.send_task_message

        def unrouted(*args, **kwargs):
            kwargs["routing_key"] = "document_platform.unrouted." + uuid4().hex
            return send(*args, **kwargs)

        app.amqp.send_task_message = unrouted
        return app

    monkeypatch.setattr(messaging, "create_celery", make_app)
    payload = {
        "version": 1,
        **{
            key: str(uuid4())
            for key in [
                "event_id",
                "document_id",
                "job_id",
                "batch_id",
                "fonds_id",
                "correlation_id",
            ]
        },
    }
    with pytest.raises(ConnectionError, match="no route"):
        messaging.publish_intake(
            intake_env[0], {"id": UUID(payload["event_id"]), "payload": payload}
        )


@pytest.mark.skipif(
    os.environ.get("RUN_RABBIT_INGESTION") != "1",
    reason="Requires approved local intake broker permissions",
)
def test_real_producer_cannot_consume_the_operational_queue(intake_env):
    from kombu.entity import Exchange, Queue

    from document_platform.infrastructure.messaging.connection import broker_connection

    with broker_connection(intake_env[0]) as connection, connection.channel() as channel:
        queue = Queue(
            "document_platform.processing",
            exchange=Exchange("document_platform.tasks", type="direct", durable=True),
            routing_key="document_platform.processing",
            durable=True,
        )(channel)
        queue.declare()
        with pytest.raises(Exception) as error:
            # A mistakenly granted delivery is never acked and returns on channel close.
            channel.basic_get(queue="document_platform.processing", no_ack=False)
        assert getattr(error.value, "reply_code", None) == 403
