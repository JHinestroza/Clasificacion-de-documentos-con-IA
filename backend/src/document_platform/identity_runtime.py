"""Composition root for runtime identity, without administrative credentials."""

from document_platform.application.identity.service import IdentityPolicy, IdentityService
from document_platform.config import Settings
from document_platform.infrastructure.passwords import ArgonPasswords
from document_platform.infrastructure.persistence.identity import PostgresUnitOfWork


def build_identity_service(settings: Settings) -> IdentityService:
    return IdentityService(
        PostgresUnitOfWork(settings),
        ArgonPasswords(settings.auth_hash_concurrency),
        IdentityPolicy(
            settings.auth_idle_seconds,
            settings.auth_absolute_seconds,
            settings.auth_login_window_seconds,
            settings.auth_login_max_attempts,
        ),
    )
