"""Prepare only the approved intake resource permissions; preserve broker identities/secrets."""

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from document_platform.config import Settings
from scripts.prepare_rabbitmq_local import _credentials_match, assert_operator, definitions

CONFIGURE = r"^document_platform[.](integration|tasks|processing|ingestion_test)$"
READ = r"^document_platform[.](integration|tasks|ingestion_test)$"


def expanded_definitions(settings: Settings, existing: dict[str, Any]) -> dict[str, Any]:
    expected = definitions(settings)
    users = existing.get("users", [])
    if len(users) != 1 or not _credentials_match(
        users[0].get("password_hash", ""), settings.broker_password.get_secret_value()
    ):
        raise ValueError("Unexpected broker identity; no credentials changed")
    expected["users"][0]["password_hash"] = users[0]["password_hash"]
    updated = copy.deepcopy(expected)
    updated["permissions"][0].update(configure=CONFIGURE, write=CONFIGURE, read=READ)
    if existing != expected and existing != updated:
        raise ValueError("Unexpected broker topology or permissions; no changes applied")
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        assert_operator()
        path = Path(__file__).resolve().parents[1] / ".local/rabbitmq/definitions.json"
        existing = json.loads(path.read_text(encoding="utf-8"))
        wanted = expanded_definitions(Settings(), existing)
        if wanted != existing:
            backup = path.with_name("definitions.before-ingestion-" + uuid4().hex + ".json")
            backup.write_bytes(path.read_bytes())
            temp = path.with_name("definitions.write-" + uuid4().hex + ".json")
            temp.write_text(json.dumps(wanted, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, path)
        print(
            "Intake permissions staged; credentials, TLS identities and existing queues preserved."
        )
    except Exception:
        print("Intake permissions preparation failed; no raw configuration printed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
