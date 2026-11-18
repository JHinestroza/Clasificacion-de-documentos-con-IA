"""Add recoverable intake and resource-scoped audit, without destructive operations."""

from alembic import op

revision = "0002_ingestion"
down_revision = "0001_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA ingestion")
    op.execute("""CREATE TABLE ingestion.fonds (
      id UUID PRIMARY KEY, name VARCHAR(100) NOT NULL, storage_key VARCHAR(64) UNIQUE NOT NULL,
      active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK(storage_key ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'))""")
    op.execute("""CREATE TABLE ingestion.user_fonds (
      user_id UUID REFERENCES identity.users(id) NOT NULL,
      fonds_id UUID REFERENCES ingestion.fonds(id) NOT NULL, PRIMARY KEY(user_id,fonds_id))""")
    op.execute("""CREATE TABLE ingestion.batches (
      id UUID PRIMARY KEY, fonds_id UUID REFERENCES ingestion.fonds(id) NOT NULL,
      actor_id UUID REFERENCES identity.users(id) NOT NULL, state VARCHAR(24) NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK(state IN ('running','pause_requested','paused','stop_requested','stopped','completed')))
    """)
    op.execute("""CREATE UNIQUE INDEX ix_one_active_batch ON ingestion.batches(fonds_id)
      WHERE state IN ('running','pause_requested','paused','stop_requested')""")
    op.execute("""CREATE TABLE ingestion.intake_items (
      id UUID PRIMARY KEY, batch_id UUID REFERENCES ingestion.batches(id) NOT NULL,
      original_name VARCHAR(255) NOT NULL, fingerprint JSONB NOT NULL, code VARCHAR(64),
      state VARCHAR(24) NOT NULL DEFAULT 'pending', reason VARCHAR(64),
      size_bytes BIGINT, sha256 CHAR(64), pages INTEGER, relative_path TEXT,
      next_at TIMESTAMPTZ NOT NULL DEFAULT now(), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(batch_id,original_name),
      CHECK(state IN ('pending','claimed','validating','finishing','admitted','skipped','failed')),
      CHECK(sha256 IS NULL OR sha256 ~ '^[a-f0-9]{64}$'))""")
    op.execute(
        "CREATE TABLE ingestion.documents (\n"
        "      id UUID PRIMARY KEY, fonds_id UUID REFERENCES "
        "ingestion.fonds(id) NOT NULL,\n"
        "      item_id UUID REFERENCES ingestion.intake_items(id) UNIQUE "
        "NOT NULL,\n"
        "      code VARCHAR(64) UNIQUE NOT NULL, sha256 CHAR(64) NOT NULL,"
        " size_bytes BIGINT NOT NULL,\n"
        "      pages INTEGER NOT NULL, relative_path TEXT NOT NULL,\n"
        "      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "CHECK(size_bytes BETWEEN 1 AND 100000000),\n"
        "      CHECK(code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'), CHECK(sha256 ~ "
        "'^[a-f0-9]{64}$'), CHECK(pages>0))"
    )
    op.execute("CREATE INDEX ix_documents_hash ON ingestion.documents(sha256)")
    op.execute("""CREATE TABLE ingestion.jobs (
      id UUID PRIMARY KEY, document_id UUID REFERENCES ingestion.documents(id) NOT NULL,
      attempt INTEGER NOT NULL CHECK(attempt>0), state VARCHAR(24) NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(document_id,attempt),
      CHECK(state IN ('pending_publish','queued')))""")
    op.execute(
        "CREATE TABLE ingestion.events (\n"
        "      id UUID PRIMARY KEY, fonds_id UUID REFERENCES "
        "ingestion.fonds(id) NOT NULL,\n"
        "      batch_id UUID REFERENCES ingestion.batches(id), item_id "
        "UUID REFERENCES ingestion.intake_items(id),\n"
        "      actor_id UUID REFERENCES identity.users(id), action "
        "VARCHAR(64) NOT NULL, reason VARCHAR(64),\n"
        "      occurred_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    op.execute("CREATE INDEX ix_events_batch ON ingestion.events(batch_id,occurred_at,id)")
    op.execute("""CREATE TABLE ingestion.file_moves (
      id UUID PRIMARY KEY, item_id UUID REFERENCES ingestion.intake_items(id) NOT NULL,
      source TEXT NOT NULL, destination TEXT NOT NULL, fingerprint JSONB NOT NULL,
      target_state VARCHAR(24) NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'pending',
      reason VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK(state IN ('pending','done','blocked')))""")
    op.execute(
        "CREATE UNIQUE INDEX ix_one_item_move ON "
        "ingestion.file_moves(item_id) WHERE state='pending'"
    )
    op.execute("""CREATE TABLE ingestion.outbox (
      id UUID PRIMARY KEY, job_id UUID REFERENCES ingestion.jobs(id) UNIQUE NOT NULL,
      payload JSONB NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'pending',
      attempts INTEGER NOT NULL DEFAULT 0, next_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      lease_until TIMESTAMPTZ, last_reason VARCHAR(64), confirmed_at TIMESTAMPTZ,
      CHECK(state IN ('pending','sending','confirmed','blocked')))""")
    op.execute(
        "ALTER TABLE identity.audit_logs ADD COLUMN fonds_id UUID REFERENCES ingestion.fonds(id)"
    )
    op.execute("CREATE INDEX ix_audit_fonds ON identity.audit_logs(fonds_id,occurred_at DESC)")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive ingestion downgrade requires a separately approved recovery plan"
    )
