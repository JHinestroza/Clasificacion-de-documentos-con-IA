"""Argon2id hashing with bounded CPU/memory concurrency."""

from threading import BoundedSemaphore

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from document_platform.domain.identity.models import RateLimited


class ArgonPasswords:
    """OWASP minimum profile; tune only after measuring the target deployment."""

    def __init__(self, concurrency: int = 2) -> None:
        self._hasher = PasswordHasher(
            time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID
        )
        self._slots = BoundedSemaphore(concurrency)

    def hash(self, password: str) -> str:
        if not self._slots.acquire(timeout=0.25):
            raise RateLimited("Authentication is busy; try again later")
        try:
            return self._hasher.hash(password)
        finally:
            self._slots.release()

    def verify(self, encoded: str, password: str) -> bool:
        if not self._slots.acquire(timeout=0.25):
            raise RateLimited("Authentication is busy; try again later")
        try:
            try:
                return self._hasher.verify(encoded, password)
            except (VerificationError, InvalidHashError):
                return False
        finally:
            self._slots.release()
