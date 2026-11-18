"""Parameterized intake SQL; transactions/authorization are owned by the use cases."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from psycopg import sql
from psycopg.types.json import Jsonb

from document_platform.application.ingestion.ports import Repository
from document_platform.config import Settings
from document_platform.domain.identity.models import ConflictError, User
from document_platform.domain.ingestion.models import PdfFacts, Record
from document_platform.infrastructure.persistence.database import connect_database
from document_platform.infrastructure.persistence.identity import IdentityRepository

ITEM_SELECT = """SELECT i.*,b.fonds_id,b.actor_id,b.state AS batch_state,f.storage_key
 FROM ingestion.intake_items i JOIN ingestion.batches b ON b.id=i.batch_id
 JOIN ingestion.fonds f ON f.id=b.fonds_id """


class IngestionRepository(IdentityRepository):
    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self.connection.transaction():
            yield

    def fonds(self, fonds_id: UUID) -> Record | None:
        return self.connection.execute(
            "SELECT * FROM ingestion.fonds WHERE id=%s", (fonds_id,)
        ).fetchone()

    def list_fonds(self, user: User) -> list[Record]:
        return self.connection.execute(
            (
                "SELECT f.* FROM ingestion.fonds f WHERE\n"
                "          (%s OR EXISTS(SELECT 1 FROM ingestion.user_fonds u "
                "WHERE u.fonds_id=f.id AND u.user_id=%s))\n"
                "          ORDER BY f.name,f.id"
            ),
            (user.is_superuser, user.id),
        ).fetchall()

    def has_access(self, user: User, fonds_id: UUID) -> bool:
        return user.is_superuser or bool(
            self.connection.execute(
                "SELECT 1 FROM ingestion.user_fonds WHERE user_id=%s AND fonds_id=%s",
                (user.id, fonds_id),
            ).fetchone()
        )

    def create_fonds(self, name: str, key: str) -> Record:
        row = self.connection.execute(
            """INSERT INTO ingestion.fonds(id,name,storage_key)
          VALUES(%s,%s,%s) ON CONFLICT(storage_key) DO NOTHING RETURNING *""",
            (uuid4(), name, key),
        ).fetchone()
        if row is None:
            raise ConflictError("Fonds already exists")
        return row

    def memberships(self, fonds_id: UUID) -> list[Record]:
        return self.connection.execute(
            "SELECT user_id FROM ingestion.user_fonds WHERE fonds_id=%s ORDER BY user_id",
            (fonds_id,),
        ).fetchall()

    def grant(self, fonds_id: UUID, user_id: UUID, enabled: bool) -> None:
        if enabled:
            self.connection.execute(
                "INSERT INTO ingestion.user_fonds VALUES(%s,%s) ON CONFLICT DO NOTHING",
                (user_id, fonds_id),
            )
        else:
            self.connection.execute(
                "DELETE FROM ingestion.user_fonds WHERE user_id=%s AND fonds_id=%s",
                (user_id, fonds_id),
            )

    def batches(self, fonds_id: UUID, limit: int, offset: int) -> list[Record]:
        return self.connection.execute(
            (
                "SELECT b.*, (SELECT count(*) FROM ingestion.intake_items i WHERE "
                "i.batch_id=b.id) AS total\n"
                "          FROM ingestion.batches b WHERE fonds_id=%s ORDER BY "
                "created_at DESC,id DESC LIMIT %s OFFSET %s"
            ),
            (fonds_id, limit, offset),
        ).fetchall()

    def batch(self, batch_id: UUID) -> Record | None:
        row = self.connection.execute(
            "SELECT * FROM ingestion.batches WHERE id=%s", (batch_id,)
        ).fetchone()
        if row is not None:
            row["counts"] = {
                r["state"]: r["n"]
                for r in self.connection.execute(
                    (
                        "SELECT CASE WHEN i.state='admitted' THEN j.state ELSE i.state END"
                        " AS state,count(*) AS n\n"
                        "              FROM ingestion.intake_items i LEFT JOIN "
                        "ingestion.documents d ON d.item_id=i.id\n"
                        "              LEFT JOIN ingestion.jobs j ON j.document_id=d.id "
                        "WHERE i.batch_id=%s GROUP BY 1"
                    ),
                    (batch_id,),
                ).fetchall()
            }
            blocked = self.connection.execute(
                (
                    "SELECT count(*) AS n FROM ingestion.outbox o JOIN ingestion.jobs "
                    "j ON j.id=o.job_id JOIN ingestion.documents d ON "
                    "d.id=j.document_id JOIN ingestion.intake_items i ON "
                    "i.id=d.item_id WHERE i.batch_id=%s AND o.state='blocked'"
                ),
                (batch_id,),
            ).fetchone()
            assert blocked is not None
            row["blocked_publications"] = blocked["n"]
        return row

    def items(
        self, batch_id: UUID, limit: int, offset: int, search: str, state: str
    ) -> list[Record]:
        return self.connection.execute(
            (
                "SELECT "
                "i.id,i.original_name,i.code,i.state,i.reason,i.size_bytes,i.sha256,i.pages,i.created_at,"
                "\n"
                "          j.state AS job_state FROM ingestion.intake_items i\n"
                "          LEFT JOIN ingestion.documents d ON d.item_id=i.id LEFT "
                "JOIN ingestion.jobs j ON j.document_id=d.id\n"
                "          WHERE i.batch_id=%s AND (%s='' OR i.original_name ILIKE"
                " %s ESCAPE '!')\n"
                "          AND (%s='' OR i.state=%s OR j.state=%s)\n"
                "          ORDER BY i.created_at,i.id LIMIT %s OFFSET %s"
            ),
            (
                batch_id,
                search,
                "%" + search.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%",
                state,
                state,
                state,
                limit,
                offset,
            ),
        ).fetchall()

    def events(self, batch_id: UUID, limit: int, offset: int) -> list[Record]:
        return self.connection.execute(
            (
                "SELECT id,item_id,actor_id,action,reason,occurred_at FROM "
                "ingestion.events WHERE batch_id=%s ORDER BY occurred_at DESC,id "
                "DESC LIMIT %s OFFSET %s"
            ),
            (batch_id, limit, offset),
        ).fetchall()

    def event(
        self,
        fonds_id: UUID,
        batch_id: UUID | None,
        item_id: UUID | None,
        actor: UUID | None,
        action: str,
        reason: str | None = None,
    ) -> None:
        self.connection.execute(
            (
                "INSERT INTO "
                "ingestion.events(id,fonds_id,batch_id,item_id,actor_id,action,reason)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s)"
            ),
            (uuid4(), fonds_id, batch_id, item_id, actor, action, reason),
        )

    def start(self, fonds_id: UUID, actor: UUID, candidates: list[Record]) -> Record:
        if self.connection.execute(
            (
                "SELECT 1 FROM ingestion.batches WHERE fonds_id=%s AND state IN "
                "('running','paused','pause_requested','stop_requested')"
            ),
            (fonds_id,),
        ).fetchone():
            raise ConflictError("A batch is already active for this fonds")
        batch_id = uuid4()
        self.connection.execute(
            "INSERT INTO ingestion.batches(id,fonds_id,actor_id,state) VALUES(%s,%s,%s,'running')",
            (batch_id, fonds_id, actor),
        )
        for candidate in candidates:
            self.connection.execute(
                (
                    "INSERT INTO "
                    "ingestion.intake_items(id,batch_id,original_name,fingerprint) "
                    "VALUES(%s,%s,%s,%s)"
                ),
                (uuid4(), batch_id, candidate["name"], Jsonb(candidate["fingerprint"])),
            )
        row = self.batch(batch_id)
        assert row is not None
        return row

    def command_batch(self, batch_id: UUID, state: str, actor: UUID | None = None) -> Record:
        self.connection.execute(
            (
                "UPDATE ingestion.batches SET "
                "state=%s,actor_id=COALESCE(%s,actor_id),updated_at=now() WHERE "
                "id=%s"
            ),
            (state, actor, batch_id),
        )
        row = self.batch(batch_id)
        assert row is not None
        return row

    def set_item(self, item_id: UUID, **values: object) -> None:
        if not values or not values.keys() <= {
            "state",
            "reason",
            "size_bytes",
            "sha256",
            "pages",
            "relative_path",
            "code",
            "next_at",
        }:
            raise ValueError("Unsupported intake update")
        fields = sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(k)) for k in values)
        self.connection.execute(
            sql.SQL("UPDATE ingestion.intake_items SET {} WHERE id=%s").format(fields),
            (*values.values(), item_id),
        )

    def make_move(
        self,
        item_id: UUID,
        source: str,
        destination: str,
        proof: dict[str, int],
        target: str,
        reason: str | None = None,
    ) -> None:
        self.connection.execute(
            (
                "INSERT INTO "
                "ingestion.file_moves(id,item_id,source,destination,fingerprint,target_state,reason)"
                " VALUES(%s,%s,%s,%s,%s,%s,%s)"
            ),
            (uuid4(), item_id, source, destination, Jsonb(proof), target, reason),
        )
        self.set_item(
            item_id, state="claimed" if target == "validating" else "finishing", reason=reason
        )

    def pending_moves(self) -> list[Record]:
        return self.connection.execute(
            "SELECT m.*,b.fonds_id,b.id AS batch_id,b.actor_id FROM "
            "ingestion.file_moves m JOIN ingestion.intake_items i ON "
            "i.id=m.item_id JOIN ingestion.batches b ON b.id=i.batch_id WHERE "
            "m.state='pending' ORDER BY m.created_at,m.id LIMIT 20"
        ).fetchall()

    def finish_move(self, move: Record) -> None:
        self.connection.execute(
            "UPDATE ingestion.file_moves SET state='done' WHERE id=%s", (move["id"],)
        )
        self.set_item(
            move["item_id"],
            state=move["target_state"],
            relative_path=move["destination"],
            reason=move["reason"],
        )
        self.event(
            move["fonds_id"],
            move["batch_id"],
            move["item_id"],
            move["actor_id"],
            "file.moved",
            move["reason"],
        )

    def block_move(self, move: Record, reason: str) -> None:
        if reason == "busy":
            self.set_item(move["item_id"], reason=reason)
            return
        self.connection.execute(
            "UPDATE ingestion.file_moves SET state='blocked',reason=%s WHERE id=%s",
            (reason, move["id"]),
        )
        self.set_item(move["item_id"], state="failed", reason=reason)
        self.event(
            move["fonds_id"],
            move["batch_id"],
            move["item_id"],
            move["actor_id"],
            "file.blocked",
            reason,
        )

    def next_item(self) -> Record | None:
        return self.connection.execute(
            ITEM_SELECT
            + (
                "WHERE i.state='validating' OR (i.state='pending' AND "
                "b.state='running' AND i.next_at<=now())\n"
                "          ORDER BY CASE WHEN i.state='validating' THEN 0 ELSE 1 "
                "END,i.created_at,i.id LIMIT 1"
            )
        ).fetchone()

    def code_exists(self, code: str) -> bool:
        return bool(
            self.connection.execute(
                "SELECT 1 FROM ingestion.documents WHERE code=%s", (code,)
            ).fetchone()
        )

    def same_content(self, sha256: str, fonds_id: UUID) -> bool:
        return bool(
            self.connection.execute(
                "SELECT 1 FROM ingestion.documents WHERE sha256=%s AND fonds_id=%s OFFSET 1",
                (sha256, fonds_id),
            ).fetchone()
        )

    def admit(self, item: Record, code: str, facts: PdfFacts) -> bool:
        doc_id, job_id, event_id = uuid4(), uuid4(), uuid4()
        inserted = self.connection.execute(
            (
                "INSERT INTO "
                "ingestion.documents(id,fonds_id,item_id,code,sha256,size_bytes,pages,relative_path)"
                "\n"
                "          VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO "
                "NOTHING RETURNING id"
            ),
            (
                doc_id,
                item["fonds_id"],
                item["id"],
                code,
                facts.sha256,
                facts.size,
                facts.pages,
                item["relative_path"],
            ),
        ).fetchone()
        if inserted is None:
            return False
        self.connection.execute(
            (
                "INSERT INTO ingestion.jobs(id,document_id,attempt,state) "
                "VALUES(%s,%s,1,'pending_publish')"
            ),
            (job_id, doc_id),
        )
        payload = {
            "version": 1,
            "event_id": str(event_id),
            "document_id": str(doc_id),
            "job_id": str(job_id),
            "batch_id": str(item["batch_id"]),
            "fonds_id": str(item["fonds_id"]),
            "correlation_id": str(item["id"]),
        }
        self.connection.execute(
            "INSERT INTO ingestion.outbox(id,job_id,payload) VALUES(%s,%s,%s)",
            (event_id, job_id, Jsonb(payload)),
        )
        self.set_item(
            item["id"],
            state="admitted",
            code=code,
            size_bytes=facts.size,
            sha256=facts.sha256,
            pages=facts.pages,
            reason=None,
        )
        return True

    def settle_batches(self) -> None:
        self.connection.execute(
            "UPDATE ingestion.batches b SET state=CASE\n"
            "          WHEN state='stop_requested' THEN 'stopped'\n"
            "          WHEN NOT EXISTS(SELECT 1 FROM ingestion.intake_items i "
            "WHERE i.batch_id=b.id AND i.state='pending') THEN 'completed'\n"
            "          WHEN state='pause_requested' THEN 'paused' ELSE state "
            "END,updated_at=now()\n"
            "          WHERE state IN "
            "('running','pause_requested','stop_requested') AND NOT EXISTS\n"
            "          (SELECT 1 FROM ingestion.intake_items i WHERE "
            "i.batch_id=b.id AND i.state IN "
            "('claimed','validating','finishing'))\n"
            "          AND (state<>'running' OR NOT EXISTS(SELECT 1 FROM "
            "ingestion.intake_items i WHERE i.batch_id=b.id AND "
            "i.state='pending'))"
        )

    def claim_outbox(self) -> Record | None:
        return self.connection.execute(
            "UPDATE ingestion.outbox SET "
            "state='sending',attempts=attempts+1,lease_until=now()+interval "
            "'60 seconds'\n"
            "          WHERE id=(SELECT id FROM ingestion.outbox WHERE "
            "(state='pending' AND next_at<=now())\n"
            "          OR (state='sending' AND lease_until<now()) ORDER BY "
            "next_at,id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *"
        ).fetchone()

    def confirm_outbox(self, event_id: UUID) -> None:
        row = self.connection.execute(
            (
                "UPDATE ingestion.outbox SET "
                "state='confirmed',confirmed_at=now(),lease_until=NULL,last_reason=NULL"
                " WHERE id=%s RETURNING job_id,payload"
            ),
            (event_id,),
        ).fetchone()
        assert row is not None
        self.connection.execute(
            "UPDATE ingestion.jobs SET state='queued' WHERE id=%s", (row["job_id"],)
        )
        payload = row["payload"]
        self.event(
            UUID(payload["fonds_id"]),
            UUID(payload["batch_id"]),
            UUID(payload["correlation_id"]),
            None,
            "publication.confirmed",
        )

    def fail_outbox(self, event_id: UUID) -> None:
        self.connection.execute(
            (
                "UPDATE ingestion.outbox SET state=CASE WHEN attempts>=10 THEN "
                "'blocked' ELSE 'pending' END,\n"
                "          "
                "next_at=now()+make_interval(secs=>LEAST(60,power(2,LEAST(attempts,6)))::double"
                " precision),\n"
                "          lease_until=NULL,last_reason='broker_unavailable' WHERE"
                " id=%s"
            ),
            (event_id,),
        )

    def retry_outbox(self, batch_id: UUID) -> None:
        self.connection.execute(
            (
                "UPDATE ingestion.outbox o SET "
                "state='pending',attempts=0,next_at=now(),lease_until=NULL\n"
                "          FROM ingestion.jobs j JOIN ingestion.documents d ON "
                "d.id=j.document_id JOIN ingestion.intake_items i ON "
                "i.id=d.item_id\n"
                "          WHERE o.job_id=j.id AND i.batch_id=%s AND "
                "o.state='blocked'"
            ),
            (batch_id,),
        )


class IngestionUnitOfWork:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def __call__(self) -> Iterator[Repository]:
        with connect_database(self.settings) as connection:
            yield IngestionRepository(connection)

    @contextmanager
    def runner_lock(self) -> Iterator[bool]:
        with connect_database(self.settings, autocommit=True) as connection:
            row = connection.execute(
                "SELECT pg_try_advisory_lock(417004004) AS acquired"
            ).fetchone()
            assert row is not None
            yield bool(row["acquired"])
