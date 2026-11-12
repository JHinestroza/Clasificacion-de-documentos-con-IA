"""Parameterized PostgreSQL adapter with atomic state/audit and serialized identity rules."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from document_platform.application.identity.ports import Repository
from document_platform.config import Settings
from document_platform.domain.identity.models import Audit, Session, User
from document_platform.infrastructure.persistence.database import connect_database

SECURITY_LOCK = 417003003
USER_SELECT = """SELECT u.*,
 ARRAY(SELECT permission_code FROM identity.user_permissions p
       WHERE p.user_id=u.id ORDER BY permission_code) AS permissions
 FROM identity.users u """


def user_record(row: dict[str, Any] | None) -> User | None:
    if row is None:
        return None
    return User(
        row["id"],
        row["username"],
        row["password_hash"],
        row["is_active"],
        row["is_superuser"],
        row["created_at"],
        row["updated_at"],
        frozenset(row["permissions"]),
    )


class IdentityRepository:
    def __init__(self, connection: psycopg.Connection[dict[str, Any]]) -> None:
        self.connection = connection

    def lock_security_state(self) -> None:
        # One lock ordering for all identity actions prevents stale revocation and last-admin races.
        self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (SECURITY_LOCK,))

    def user_by_name(self, name: str) -> User | None:
        return user_record(
            self.connection.execute(USER_SELECT + "WHERE u.username=%s", (name,)).fetchone()
        )

    def user_by_id(self, user_id: UUID) -> User | None:
        return user_record(
            self.connection.execute(USER_SELECT + "WHERE u.id=%s", (user_id,)).fetchone()
        )

    def insert_user(self, user: User) -> None:
        self.connection.execute(
            """INSERT INTO identity.users
            (id,username,password_hash,is_active,is_superuser,created_at,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                user.id,
                user.username,
                user.password_hash,
                user.is_active,
                user.is_superuser,
                user.created_at,
                user.updated_at,
            ),
        )

    def save_user(self, user: User) -> None:
        self.connection.execute(
            """UPDATE identity.users SET password_hash=%s,is_active=%s,
            is_superuser=%s,updated_at=%s WHERE id=%s""",
            (user.password_hash, user.is_active, user.is_superuser, user.updated_at, user.id),
        )

    def list_users(self, limit: int, offset: int) -> list[User]:
        rows = self.connection.execute(
            USER_SELECT + "ORDER BY u.created_at,u.id LIMIT %s OFFSET %s", (limit, offset)
        ).fetchall()
        return [user for row in rows if (user := user_record(row)) is not None]

    def count_superusers(self, *, active_only: bool) -> int:
        row = self.connection.execute(
            """SELECT count(*) AS count FROM identity.users
            WHERE is_superuser AND (NOT %s OR is_active)""",
            (active_only,),
        ).fetchone()
        assert row is not None
        return int(row["count"])

    def set_permissions(self, user_id: UUID, permissions: frozenset[str]) -> None:
        self.connection.execute(
            "DELETE FROM identity.user_permissions WHERE user_id=%s", (user_id,)
        )
        for permission in sorted(permissions):
            self.connection.execute(
                "INSERT INTO identity.user_permissions(user_id,permission_code) VALUES (%s,%s)",
                (user_id, permission),
            )

    def session(self, token_hash: str) -> Session | None:
        row = self.connection.execute(
            "SELECT * FROM identity.sessions WHERE token_hash=%s", (token_hash,)
        ).fetchone()
        return Session(**row) if row else None

    def insert_session(self, session: Session) -> None:
        self.connection.execute(
            """INSERT INTO identity.sessions
            (token_hash,user_id,csrf_hash,created_at,last_seen_at,expires_at,revoked_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                session.token_hash,
                session.user_id,
                session.csrf_hash,
                session.created_at,
                session.last_seen_at,
                session.expires_at,
                session.revoked_at,
            ),
        )

    def save_session(self, session: Session) -> None:
        self.connection.execute(
            "UPDATE identity.sessions SET last_seen_at=%s,revoked_at=%s WHERE token_hash=%s",
            (session.last_seen_at, session.revoked_at, session.token_hash),
        )

    def revoke_sessions(self, user_id: UUID, at: datetime) -> None:
        self.connection.execute(
            "UPDATE identity.sessions SET revoked_at=%s WHERE user_id=%s AND revoked_at IS NULL",
            (at, user_id),
        )

    def failures(self, subject: str, since: datetime) -> int:
        row = self.connection.execute(
            """SELECT count(*) AS count FROM identity.audit_logs
          WHERE action='auth.login' AND outcome='denied' AND subject_hash=%s AND occurred_at>%s""",
            (subject, since),
        ).fetchone()
        assert row is not None
        return int(row["count"])

    def audit(self, entry: Audit) -> None:
        self.connection.execute(
            """INSERT INTO identity.audit_logs
            (id,actor_id,action,resource_id,outcome,occurred_at,reason,subject_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                entry.id,
                entry.actor_id,
                entry.action,
                entry.resource_id,
                entry.outcome,
                entry.occurred_at,
                entry.reason,
                entry.subject_hash,
            ),
        )

    def list_audit(self, limit: int, offset: int) -> list[Audit]:
        rows = self.connection.execute(
            "SELECT * FROM identity.audit_logs "
            "ORDER BY occurred_at DESC,id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
        return [Audit(**row) for row in rows]


class PostgresUnitOfWork:
    """Commit normally; roll back state and audit together on every exception."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def __call__(self) -> Iterator[Repository]:
        with connect_database(self.settings) as connection:
            yield IdentityRepository(connection)
