"""Explicit database/migration/bootstrap commands; no secrets are printed."""

import argparse
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql

from document_platform.config import BootstrapSettings, DatabaseAdminSettings
from document_platform.domain.identity.models import ConflictError
from document_platform.identity_runtime import build_identity_service
from document_platform.infrastructure.persistence.database import connect_database


def migration_config(settings: DatabaseAdminSettings | None = None) -> Config:
    backend = Path(__file__).resolve().parents[2]
    configuration = Config(str(backend / "alembic.ini"))
    if settings is not None:
        configuration.attributes["database_settings"] = settings
    return configuration


def initialize_database(settings: DatabaseAdminSettings) -> None:
    """Provision the project without dropping data or rotating existing credentials."""
    if not re.fullmatch(r"document_platform(?:_test_[a-f0-9]+)?", settings.db_name):
        raise ValueError(
            "Provisioning only supports project and uniquely named synthetic databases"
        )
    if settings.db_user != "document_app":
        raise ValueError("The local TLS access policy requires the document_app role")
    with connect_database(settings, database="postgres", admin=True, autocommit=True) as connection:
        role = connection.execute(
            "SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,"
            "rolbypassrls,rolinherit "
            "FROM pg_roles WHERE rolname=%s",
            (settings.db_user,),
        ).fetchone()
        if role is None:
            verifier = connection.pgconn.encrypt_password(
                settings.db_password.get_secret_value().encode(),
                settings.db_user.encode(),
                b"scram-sha-256",
            ).decode()
            connection.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS NOINHERIT PASSWORD {}"
                ).format(sql.Identifier(settings.db_user), sql.Literal(verifier))
            )
        elif not role["rolcanlogin"] or any(
            role[name]
            for name in (
                "rolsuper",
                "rolcreatedb",
                "rolcreaterole",
                "rolreplication",
                "rolbypassrls",
                "rolinherit",
            )
        ):
            raise ValueError(
                "Existing application role has unexpected privileges; review it manually"
            )
        memberships = connection.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=%s",
            (settings.db_user,),
        ).fetchone()
        if memberships:
            raise ValueError("Existing role memberships require manual review")
        existing = connection.execute(
            "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=%s",
            (settings.db_name,),
        ).fetchone()
        if existing is None:
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(settings.db_name), sql.Identifier(settings.db_admin_user)
                )
            )
        elif existing["owner"] != settings.db_admin_user:
            raise ValueError("Existing project database has an unexpected owner")
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(settings.db_name)
            )
        )
        connection.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
                sql.Identifier(settings.db_name), sql.Identifier(settings.db_user)
            )
        )
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(settings.db_name), sql.Identifier(settings.db_user)
            )
        )
    command.upgrade(migration_config(settings), "head")
    with connect_database(settings, admin=True) as connection:
        role_name = sql.Identifier(settings.db_user)
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        connection.execute("REVOKE ALL ON SCHEMA identity FROM PUBLIC")
        for schema in ("public", "identity"):
            connection.execute(
                sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(sql.Identifier(schema), role_name)
            )
        connection.execute(
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA identity FROM {}").format(role_name)
        )
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA identity TO {}").format(role_name))
        for table in ("users", "sessions"):
            connection.execute(
                sql.SQL("GRANT SELECT,INSERT,UPDATE ON identity.{} TO {}").format(
                    sql.Identifier(table), role_name
                )
            )
        connection.execute(sql.SQL("GRANT SELECT ON identity.permissions TO {}").format(role_name))
        connection.execute(
            sql.SQL("GRANT SELECT,INSERT,DELETE ON identity.user_permissions TO {}").format(
                role_name
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT,INSERT ON identity.audit_logs TO {}").format(role_name)
        )
        connection.execute(
            sql.SQL(
                "REVOKE UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON identity.audit_logs FROM {}"
            ).format(role_name)
        )
    with connect_database(settings) as connection:
        connection.execute("SELECT id FROM identity.users LIMIT 1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init-db", "create-superuser"))
    args = parser.parse_args()
    try:
        if args.command == "init-db":
            initialize_database(DatabaseAdminSettings())
            print("Database migrated over verified TLS; application privileges restricted.")
        else:
            settings = BootstrapSettings()
            service = build_identity_service(settings)
            try:
                user = service.bootstrap_superuser(
                    settings.bootstrap_admin_username,
                    settings.bootstrap_admin_password.get_secret_value(),
                )
            except ConflictError:
                print("Superuser initialization already performed; no password was changed.")
            else:
                print("Portal superuser created: " + user.username + "; password was not printed.")
    except Exception:
        print("Identity administration failed; check TLS, credentials and migration state.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
