"""Explicit verified PostgreSQL connections; administrative settings never serve HTTP."""

from typing import Any

import psycopg
from psycopg.rows import dict_row

from document_platform.config import DatabaseAdminSettings, Settings


def connect_database(
    settings: Settings,
    *,
    database: str | None = None,
    admin: bool = False,
    autocommit: bool = False,
) -> psycopg.Connection[dict[str, Any]]:
    user = settings.db_user
    password = settings.db_password
    if admin:
        if not isinstance(settings, DatabaseAdminSettings):
            raise ValueError("Administrative settings are required")
        user, password = settings.db_admin_user, settings.db_admin_password
    connection = psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=database or settings.db_name,
        user=user,
        password=password.get_secret_value(),
        row_factory=dict_row,
        sslmode="verify-full",
        sslrootcert=str(settings.tls_ca_file),
        ssl_min_protocol_version="TLSv1.2",
        gssencmode="disable",
        connect_timeout=settings.dependency_timeout_seconds,
        autocommit=autocommit,
        application_name="document-platform",
        options=(
            f"-c statement_timeout={settings.dependency_timeout_seconds * 1000} "
            f"-c lock_timeout={settings.dependency_timeout_seconds * 1000} -c timezone=UTC"
        ),
    )
    if not connection.pgconn.ssl_in_use:
        connection.close()
        raise ConnectionError("Verified PostgreSQL TLS is required")
    return connection
