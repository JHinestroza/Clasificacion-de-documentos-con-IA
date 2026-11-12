"""Pure policy/cryptography checks do not require PostgreSQL."""

import pytest

from document_platform.application.identity.service import IdentityPolicy
from document_platform.domain.identity.models import (
    IdentityError,
    RateLimited,
    normalize_username,
    validate_password,
)
from document_platform.infrastructure.passwords import ArgonPasswords


@pytest.mark.parametrize("name", ["ad'min", "admín", "Kevin", "x", "x" * 65, "admin user"])
def test_username_policy_rejects_ambiguous_or_invalid_names(name: str) -> None:
    with pytest.raises(IdentityError):
        normalize_username(name)


def test_ascii_username_case_is_canonical() -> None:
    assert normalize_username("Some.Admin_2") == "some.admin_2"


@pytest.mark.parametrize(
    "password", ["short", " " * 20, "x" * 129, "x" * 20 + "\0", "x" * 20 + "\n"]
)
def test_password_policy(password: str) -> None:
    with pytest.raises(IdentityError):
        validate_password(password)


def test_argon2id_has_random_salts_and_no_plaintext() -> None:
    hasher = ArgonPasswords()
    password = "Synthetic long passphrase 2026!"
    first, second = hasher.hash(password), hasher.hash(password)
    assert first != second and first.startswith("$argon2id$")
    assert password not in first
    assert hasher.verify(first, password)
    assert not hasher.verify(first, "incorrect")
    assert not hasher.verify("invalid-stored-hash", password)


def test_hash_concurrency_is_bounded() -> None:
    hasher = ArgonPasswords(1)
    assert hasher._slots.acquire(blocking=False)
    try:
        with pytest.raises(RateLimited):
            hasher.hash("a" * 20)
        with pytest.raises(RateLimited):
            hasher.verify("invalid", "a" * 20)
    finally:
        hasher._slots.release()


def test_invalid_session_policy_is_rejected() -> None:
    with pytest.raises(ValueError):
        IdentityPolicy(idle_seconds=61, absolute_seconds=60)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8443",
        "https://localhost/path",
        "https://user:pass@localhost",
        "https://localhost/?q=1",
    ],
)
def test_settings_require_exact_https_origins(settings_values: dict, origin: str) -> None:
    from pydantic import ValidationError

    from document_platform.config import Settings

    with pytest.raises(ValidationError):
        Settings(**settings_values, auth_allowed_origins=(origin,))


def test_settings_reject_inconsistent_session_durations(settings_values: dict) -> None:
    from pydantic import ValidationError

    from document_platform.config import Settings

    with pytest.raises(ValidationError):
        Settings(**settings_values, auth_idle_seconds=9000, auth_absolute_seconds=600)
