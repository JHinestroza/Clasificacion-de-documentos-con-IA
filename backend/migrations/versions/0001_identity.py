"""Initial local identity schema; no destructive downgrade is provided."""

from alembic import op

revision = "0001_identity"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA identity")
    op.execute("""CREATE TABLE identity.users (
        id UUID PRIMARY KEY, username VARCHAR(64) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
        is_active BOOLEAN NOT NULL, is_superuser BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
        CHECK (username ~ '^[a-z0-9_.-]{3,64}$'))""")
    op.execute("CREATE TABLE identity.permissions(code VARCHAR(64) PRIMARY KEY)")
    op.execute("""CREATE TABLE identity.user_permissions(
        user_id UUID NOT NULL REFERENCES identity.users(id),
        permission_code VARCHAR(64) NOT NULL REFERENCES identity.permissions(code),
        PRIMARY KEY(user_id,permission_code))""")
    op.execute("""CREATE TABLE identity.sessions(
        token_hash CHAR(64) PRIMARY KEY CHECK(token_hash ~ '^[a-f0-9]{64}$'),
        user_id UUID NOT NULL REFERENCES identity.users(id),
        csrf_hash CHAR(64) NOT NULL CHECK(csrf_hash ~ '^[a-f0-9]{64}$'),
        created_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ,
        CHECK(expires_at > created_at))""")
    op.execute("CREATE INDEX ix_sessions_user ON identity.sessions(user_id)")
    op.execute(
        "CREATE INDEX ix_sessions_expiry ON identity.sessions(expires_at) WHERE revoked_at IS NULL"
    )
    op.execute("""CREATE TABLE identity.audit_logs(
        id UUID PRIMARY KEY, actor_id UUID REFERENCES identity.users(id),
        action VARCHAR(64) NOT NULL, resource_id UUID,
        outcome VARCHAR(16) NOT NULL CHECK(outcome IN ('ok','denied','throttled')),
        occurred_at TIMESTAMPTZ NOT NULL, reason VARCHAR(500),
        subject_hash CHAR(64) CHECK(subject_hash ~ '^[a-f0-9]{64}$'))""")
    op.execute("CREATE INDEX ix_audit_time ON identity.audit_logs(occurred_at DESC,id DESC)")
    op.execute("""CREATE INDEX ix_login_failures ON identity.audit_logs(subject_hash,occurred_at)
                  WHERE action='auth.login' AND outcome='denied'""")
    # This revision's catalog is immutable; later catalog changes need a new migration.
    for code in (
        "documents.read",
        "documents.content.read",
        "dashboard.read",
        "reports.read",
        "processing.start",
        "processing.pause",
        "processing.stop",
        "failed.read",
        "failed.retry",
        "failed.dismiss",
        "audit.read",
    ):
        op.execute("INSERT INTO identity.permissions(code) VALUES ('" + code + "')")


def downgrade() -> None:
    raise RuntimeError(
        "Destructive identity downgrade requires a separately approved recovery plan"
    )
