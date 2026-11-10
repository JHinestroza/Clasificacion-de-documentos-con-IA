"""Dependency readiness without exposing low-level connection failures."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from document_platform.config import Settings
from document_platform.infrastructure.messaging.connection import check_broker
from document_platform.infrastructure.persistence.connection import check_postgres

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadinessService:
    """Run dependency probes and disclose only their availability."""

    postgres_probe: Callable[[], None]
    broker_probe: Callable[[], None]

    def check(self) -> dict[str, str]:
        """Return stable status codes; never log exception bodies or connection URLs."""
        statuses: dict[str, str] = {}
        for name, probe in (("database", self.postgres_probe), ("broker", self.broker_probe)):
            try:
                probe()
            except Exception:
                logger.warning("dependency_unavailable dependency=%s", name)
                statuses[name] = "unavailable"
            else:
                statuses[name] = "ok"
        return statuses

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReadinessService":
        """Bind infrastructure probes without opening connections during construction."""
        return cls(partial(check_postgres, settings), partial(check_broker, settings))
