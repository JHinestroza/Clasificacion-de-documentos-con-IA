"""Identity records and public views; credentials never appear in representations."""

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

PERMISSIONS = frozenset(
    {
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
    }
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
USERNAME_PATTERN = re.compile(r"[a-z0-9_.-]{3,64}")


class IdentityError(Exception):
    """Stable public error; messages must not include credentials or internal failures."""

    status = 400


class AuthenticationError(IdentityError):
    status = 401


class PermissionDenied(IdentityError):
    status = 403


class ConflictError(IdentityError):
    status = 409


class RateLimited(IdentityError):
    status = 429


@dataclass(frozen=True)
class User:
    id: UUID
    username: str
    password_hash: str = field(repr=False)
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    permissions: frozenset[str] = frozenset()

    def public(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "username": self.username,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "permissions": sorted(self.permissions),
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class Session:
    token_hash: str = field(repr=False)
    user_id: UUID
    csrf_hash: str = field(repr=False)
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class Audit:
    id: UUID
    actor_id: UUID | None
    action: str
    resource_id: UUID | None
    outcome: str
    occurred_at: datetime
    reason: str | None = None
    subject_hash: str | None = field(default=None, repr=False)

    def public(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "action": self.action,
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "outcome": self.outcome,
            "occurred_at": self.occurred_at.isoformat(),
            "reason": self.reason,
        }


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for_token(token: str) -> str:
    """Derive a stable CSRF challenge without storing the raw session identifier."""
    return hmac.new(token.encode(), b"document-platform-csrf-v1", hashlib.sha256).hexdigest()


def normalize_username(value: str) -> str:
    normalized = value.casefold()
    if not value.isascii() or USERNAME_PATTERN.fullmatch(normalized) is None:
        raise IdentityError(
            "Username must contain 3 to 64 ASCII letters, digits, dots, underscores or hyphens"
        )
    return normalized


def validate_password(password: str) -> None:
    if (
        not 16 <= len(password) <= 128
        or not password.strip()
        or any(c in password for c in "\r\n\0")
    ):
        raise IdentityError("Password must contain 16 to 128 nonblank single-line characters")
