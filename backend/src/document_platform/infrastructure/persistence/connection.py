"""Minimal PostgreSQL health check with mandatory verified TLS."""

import psycopg

from document_platform.config import Settings


def check_postgres(settings: Settings) -> None:
    """Connect over TLS and run a bounded, read-only probe without changing data."""
    with psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        sslmode="verify-full",
        sslrootcert=str(settings.tls_ca_file),
        ssl_min_protocol_version="TLSv1.2",
        gssencmode="disable",
        connect_timeout=settings.dependency_timeout_seconds,
        options=f"-c statement_timeout={settings.dependency_timeout_seconds * 1000}",
        autocommit=True,
    ) as connection:
        if not connection.pgconn.ssl_in_use:
            raise ConnectionError("Database connection did not use TLS")
        if connection.execute("SELECT 1").fetchone() != (1,):
            raise ConnectionError("Database readiness probe did not succeed")
        schema = connection.execute(
            "SELECT to_regclass('identity.users') IS NOT NULL "
            "AND to_regclass('identity.sessions') IS NOT NULL "
            "AND to_regclass('identity.audit_logs') IS NOT NULL"
        ).fetchone()
        if schema is None or schema[0] is not True:
            raise ConnectionError("Identity migrations are not ready")
