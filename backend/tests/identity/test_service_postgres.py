"""Transactions, revocation and concurrency against PostgreSQL, not SQLite or memory."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest

from document_platform.application.identity.service import IdentityPolicy, IdentityService
from document_platform.domain.identity.models import (
    AuthenticationError,
    ConflictError,
    PermissionDenied,
    RateLimited,
    digest,
)
from document_platform.infrastructure.passwords import ArgonPasswords
from document_platform.infrastructure.persistence.database import connect_database
from document_platform.infrastructure.persistence.identity import (
    IdentityRepository,
    PostgresUnitOfWork,
)

from .conftest import TEST_PASSWORD, new_environment


def test_argon2id_storage_login_and_public_redaction(account: tuple) -> None:
    settings, service, admin, login, user = account
    assert user.password_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert TEST_PASSWORD not in repr(user) + str(user.public())
    signed = service.login(user.username.upper(), TEST_PASSWORD)
    assert signed.token not in repr(signed)
    with connect_database(settings) as connection:
        row = connection.execute(
            "SELECT token_hash,csrf_hash FROM identity.sessions "
            "WHERE user_id=%s ORDER BY created_at DESC",
            (user.id,),
        ).fetchone()
        assert row["token_hash"] == digest(signed.token)
        assert signed.token not in str(row) and signed.csrf_token not in str(row)
    with pytest.raises(AuthenticationError, match="Invalid credentials"):
        service.login(user.username, "incorrect-synthetic-password")
    assert service.me(signed.token).id == user.id


def test_permission_grant_revokes_old_sessions_and_enforces_audit(account: tuple) -> None:
    settings, service, admin, login, user = account
    signed = service.login(user.username, TEST_PASSWORD)
    with pytest.raises(PermissionDenied):
        service.list_users(signed.token)
    with pytest.raises(PermissionDenied):
        service.list_audit(signed.token)
    service.set_permissions(
        login.token,
        login.csrf_token,
        user.id,
        frozenset({"audit.read"}),
        "Synthetic permission grant",
    )
    with pytest.raises(AuthenticationError):
        service.me(signed.token)
    refreshed = service.login(user.username, TEST_PASSWORD)
    assert service.list_audit(refreshed.token)
    with pytest.raises(PermissionDenied):
        service.list_users(refreshed.token)
    service.set_permissions(
        login.token, login.csrf_token, user.id, frozenset(), "Synthetic permission revocation"
    )
    with pytest.raises(AuthenticationError):
        service.me(refreshed.token)


def test_password_change_and_disable_revoke_all_sessions(account: tuple) -> None:
    settings, service, admin, login, user = account
    first = service.login(user.username, TEST_PASSWORD)
    second = service.login(user.username, TEST_PASSWORD)
    replacement = "New-synthetic-password-with-entropy!"
    service.change_password(first.token, first.csrf_token, TEST_PASSWORD, replacement)
    for token in (first.token, second.token):
        with pytest.raises(AuthenticationError):
            service.me(token)
    with pytest.raises(AuthenticationError):
        service.login(user.username, TEST_PASSWORD)
    fresh = service.login(user.username, replacement)
    service.set_active(login.token, login.csrf_token, user.id, False, "Synthetic account disable")
    with pytest.raises(AuthenticationError):
        service.me(fresh.token)
    with pytest.raises(AuthenticationError):
        service.login(user.username, replacement)
    service.set_active(login.token, login.csrf_token, user.id, True, "Synthetic account enable")
    assert service.login(user.username, replacement)


def test_logout_and_relogin_revoke_previous_token(account: tuple) -> None:
    settings, service, admin, login, user = account
    first = service.login(user.username, TEST_PASSWORD)
    second = service.login(user.username, TEST_PASSWORD, previous_token=first.token)
    with pytest.raises(AuthenticationError):
        service.me(first.token)
    service.logout(second.token, second.csrf_token)
    with pytest.raises(AuthenticationError):
        service.me(second.token)


def test_csrf_binding_and_self_permission_assignment(account: tuple) -> None:
    settings, service, admin, login, user = account
    with pytest.raises(PermissionDenied):
        service.set_active(login.token, "incorrect-csrf", user.id, False, "Must not apply")
    assert service.me(service.login(user.username, TEST_PASSWORD).token).is_active
    with pytest.raises(PermissionDenied):
        service.set_permissions(
            login.token,
            login.csrf_token,
            admin.id,
            frozenset({"audit.read"}),
            "Self grant must fail",
        )
    with pytest.raises(ConflictError):
        service.bootstrap_superuser("another_admin", TEST_PASSWORD)
    with pytest.raises(ConflictError):
        service.create_user(login.token, login.csrf_token, user.username.upper(), TEST_PASSWORD)


@pytest.mark.parametrize("known", [False, True])
def test_failed_login_control_is_persistent_bounded_and_expires(
    account: tuple, known: bool
) -> None:
    settings, base, admin, login, user = account
    now = [datetime.now(UTC)]
    policy = IdentityPolicy(30, 60, 30, 2)
    service = IdentityService(
        PostgresUnitOfWork(settings), ArgonPasswords(), policy, lambda: now[0]
    )
    username = user.username if known else "unknown_" + uuid4().hex[:16]
    for _ in range(2):
        with pytest.raises(AuthenticationError):
            service.login(username, "wrong-synthetic-password")
    with pytest.raises(RateLimited):
        service.login(username, TEST_PASSWORD)
    # Reconstructing the service does not reset the persisted attempts.
    reconstructed = IdentityService(
        PostgresUnitOfWork(settings), ArgonPasswords(), policy, lambda: now[0]
    )
    with pytest.raises(RateLimited):
        reconstructed.login(username, TEST_PASSWORD)
    now[0] += timedelta(seconds=31)
    if known:
        assert reconstructed.login(username, TEST_PASSWORD)
    else:
        with pytest.raises(AuthenticationError):
            reconstructed.login(username, TEST_PASSWORD)


@pytest.mark.parametrize("elapsed", [31, 61])
def test_idle_and_absolute_session_expiry(account: tuple, elapsed: int) -> None:
    settings, base, admin, login, user = account
    now = [datetime.now(UTC)]
    service = IdentityService(
        PostgresUnitOfWork(settings),
        ArgonPasswords(),
        IdentityPolicy(30, 60, 30, 5),
        lambda: now[0],
    )
    signed = service.login(user.username, TEST_PASSWORD)
    if elapsed == 61:
        now[0] += timedelta(seconds=25)
        service.me(signed.token)
        now[0] += timedelta(seconds=25)
        service.me(signed.token)
        now[0] += timedelta(seconds=11)
    else:
        now[0] += timedelta(seconds=elapsed)
    with pytest.raises(AuthenticationError):
        service.me(signed.token)


def test_audit_failure_rolls_back_account_change(account: tuple) -> None:
    settings, service, admin, login, user = account
    with (
        patch.object(
            IdentityRepository, "audit", side_effect=RuntimeError("synthetic audit failure")
        ),
        pytest.raises(RuntimeError),
    ):
        service.set_active(login.token, login.csrf_token, user.id, False, "Rollback verification")
    with connect_database(settings) as connection:
        assert connection.execute(
            "SELECT is_active FROM identity.users WHERE id=%s", (user.id,)
        ).fetchone()["is_active"]
        assert not connection.execute(
            "SELECT 1 FROM identity.audit_logs "
            "WHERE resource_id=%s AND reason='Rollback verification'",
            (user.id,),
        ).fetchone()


def test_runtime_role_cannot_modify_audit_or_create_schema(pg_environment: tuple) -> None:
    settings, service, admin = pg_environment
    with connect_database(settings) as connection:
        role = connection.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls "
            "FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert not any(role.values())
        for permission in ("UPDATE", "DELETE", "TRUNCATE"):
            allowed = connection.execute(
                "SELECT has_table_privilege(current_user,%s,%s) AS allowed",
                ("identity.audit_logs", permission),
            ).fetchone()
            assert allowed["allowed"] is False
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute("UPDATE identity.audit_logs SET reason=reason WHERE false")
        connection.rollback()
        assert not connection.execute(
            "SELECT has_schema_privilege(current_user,'public','CREATE') AS allowed"
        ).fetchone()["allowed"]


def test_two_concurrent_disables_leave_one_active_superuser(pg_environment: tuple) -> None:
    settings, service, admin = new_environment()
    first = service.login(admin.username, TEST_PASSWORD)
    second_user = service.create_user(
        first.token, first.csrf_token, "second_admin", TEST_PASSWORD, True
    )
    second = service.login(second_user.username, TEST_PASSWORD)
    barrier = Barrier(2)

    def disable(item: tuple) -> str:
        signed, user = item
        barrier.wait(timeout=5)
        try:
            service.set_active(
                signed.token, signed.csrf_token, user.id, False, "Concurrent self-disable test"
            )
        except ConflictError:
            return "protected"
        return "disabled"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(disable, [(first, admin), (second, second_user)]))
    assert sorted(results) == ["disabled", "protected"]
    with connect_database(settings) as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS count FROM identity.users WHERE is_active AND is_superuser"
            ).fetchone()["count"]
            == 1
        )


def test_reprovisioning_restores_privileges_without_replacing_accounts(
    pg_environment: tuple,
) -> None:
    from document_platform.identity_admin import initialize_database

    settings, service, admin = pg_environment
    with connect_database(settings, admin=True) as connection:
        connection.execute("GRANT CREATE ON SCHEMA public TO document_app")
        connection.execute("GRANT UPDATE ON identity.audit_logs TO document_app")
    initialize_database(settings)
    signed = service.login(admin.username, TEST_PASSWORD)
    assert service.me(signed.token).id == admin.id
    with connect_database(settings) as connection:
        assert (
            connection.execute(
                "SELECT has_table_privilege(current_user,'identity.audit_logs','UPDATE') "
                "OR has_schema_privilege(current_user,'public','CREATE') AS allowed"
            ).fetchone()["allowed"]
            is False
        )
