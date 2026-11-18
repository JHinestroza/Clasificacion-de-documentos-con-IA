"""Compose and operate intake locally as the real operator; no Celery worker in Windows."""

import argparse
import os
import subprocess
import time
from pathlib import Path

from document_platform.application.identity.service import IdentityService
from document_platform.application.ingestion.runner import IntakeRunner
from document_platform.application.ingestion.service import IngestionService
from document_platform.config import BootstrapSettings, Settings
from document_platform.identity_runtime import build_identity_service
from document_platform.infrastructure.messaging.intake import publish_intake
from document_platform.infrastructure.operator import operator
from document_platform.infrastructure.persistence.ingestion import IngestionUnitOfWork
from document_platform.infrastructure.storage.intake import IntakeStorage
from document_platform.infrastructure.storage.pdf import pdf_pages


def build_ingestion_service(settings: Settings, identity: IdentityService) -> IngestionService:
    return IngestionService(
        IngestionUnitOfWork(settings),
        identity,
        IntakeStorage(settings.storage_root),
        settings.intake_batch_limit,
    )


def build_runner(settings: Settings) -> IntakeRunner:
    uow = IngestionUnitOfWork(settings)
    storage = IntakeStorage(settings.storage_root)
    return IntakeRunner(
        uow,
        storage,
        lambda relative: pdf_pages(storage.path(relative), settings),
        lambda event: publish_intake(settings, event),
        uow.runner_lock,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--once", action="store_true")
    sub.add_parser("init-local")
    deposit = sub.add_parser("deposit")
    deposit.add_argument("source", type=Path)
    deposit.add_argument("--fonds", default="UFM")
    args = parser.parse_args()
    try:
        account = operator()
        settings = Settings()
        storage = IntakeStorage(settings.storage_root)
        if args.command == "init-local":
            bootstrap = BootstrapSettings()
            identity = build_identity_service(settings)
            service = build_ingestion_service(settings, identity)
            login = identity.login(
                bootstrap.bootstrap_admin_username,
                bootstrap.bootstrap_admin_password.get_secret_value(),
            )
            try:
                fonds = service.fonds(login.token)
                if not any(f["storage_key"] == "UFM" for f in fonds):
                    service.create_fonds(login.token, login.csrf_token, "UFM", "UFM")
                storage.ensure("UFM")
                if os.name == "nt":
                    subprocess.run(
                        [
                            "icacls",
                            str(storage.root),
                            "/inheritance:r",
                            "/grant:r",
                            f"{account}:(OI)(CI)(F)",
                            "*S-1-5-18:(OI)(CI)(F)",
                            "*S-1-5-32-544:(OI)(CI)(F)",
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                    )
                else:
                    storage.root.chmod(0o700)
                print("UFM initialized; private inbox: " + str(storage.root / "UFM" / "incoming"))
            finally:
                identity.logout(login.token, login.csrf_token)
        elif args.command == "deposit":
            print("Complete PDF deposited: " + str(storage.deposit(args.source, args.fonds)))
        else:
            runner = build_runner(settings)
            print("Intake runner started; metadata processing is not enabled.")
            while True:
                try:
                    worked = runner.step()
                except Exception:
                    print("intake_cycle_unavailable; state preserved; no raw diagnostics printed.")
                    if args.once:
                        return 1
                    worked = False
                if args.once:
                    break
                time.sleep(0.25 if worked else 1)
    except KeyboardInterrupt:
        print("Intake runner stopped; durable state preserved.")
    except Exception:
        print("Intake command failed; check operator, TLS, permissions and configuration.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
