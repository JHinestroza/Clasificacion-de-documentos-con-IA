"""Offline SQL needs no settings/secrets; online migration always verifies TLS."""

from alembic import context
from psycopg.rows import tuple_row
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from document_platform.config import DatabaseAdminSettings
from document_platform.infrastructure.persistence.database import connect_database


def run() -> None:
    if context.is_offline_mode():
        context.configure(
            url="postgresql+psycopg://", literal_binds=True, dialect_opts={"paramstyle": "named"}
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    settings = context.config.attributes.get("database_settings") or DatabaseAdminSettings()

    def connect():
        connection = connect_database(settings, admin=True)
        connection.row_factory = tuple_row
        return connection

    engine = create_engine(
        "postgresql+psycopg://",
        creator=connect,
        poolclass=NullPool,
        echo=False,
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run()
