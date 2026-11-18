"""Recoverable single-step intake orchestration, independent of HTTP and broker clients."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from uuid import uuid4

from document_platform.application.ingestion.ports import Repository, Storage, UnitOfWork
from document_platform.domain.identity.models import Audit
from document_platform.domain.ingestion.models import IntakeFault, PdfFacts, Record, document_code


class IntakeRunner:
    """Serialize a step across processes; never hold the security lock while parsing/networking."""

    def __init__(
        self,
        uow: UnitOfWork,
        storage: Storage,
        validate: Callable[[str], int],
        publish: Callable[[Record], None],
        lock: Callable[[], AbstractContextManager[bool]],
    ) -> None:
        self.uow, self.storage, self.validate, self.publish, self.lock = (
            uow,
            storage,
            validate,
            publish,
            lock,
        )

    def _event(
        self, repo: Repository, item: Record, action: str, reason: str | None = None
    ) -> None:
        repo.event(item["fonds_id"], item["batch_id"], item["id"], item["actor_id"], action, reason)
        repo.audit(
            Audit(
                uuid4(),
                item["actor_id"],
                action,
                item["id"],
                "ok",
                datetime.now(UTC),
                reason,
                fonds_id=item["fonds_id"],
            )
        )

    @staticmethod
    def _allowed(repo: Repository, item: Record) -> bool:
        user = repo.user_by_id(item["actor_id"])
        fonds = repo.fonds(item["fonds_id"])
        return bool(
            user
            and user.is_active
            and fonds
            and fonds["active"]
            and (user.is_superuser or "processing.start" in user.permissions)
            and repo.has_access(user, item["fonds_id"])
        )

    def reconcile(self) -> bool:
        changed = False
        with self.uow() as repo:
            moves = repo.pending_moves()
        for move in moves:
            reason = None
            try:
                self.storage.complete_move(move["source"], move["destination"], move["fingerprint"])
            except IntakeFault as exc:
                reason = str(exc)
            except OSError:
                reason = "storage_unavailable"
            with self.uow() as repo:
                if reason:
                    repo.block_move(move, reason)
                else:
                    repo.finish_move(move)
                    changed = True
        return changed

    def _claim(self, repo: Repository, item: Record) -> None:
        if not self._allowed(repo, item):
            repo.command_batch(item["batch_id"], "paused")
            repo.set_item(item["id"], reason="access_revoked")
            self._event(repo, item, "batch.access_revoked", "access_revoked")
        elif item["fingerprint"].get("unsafe"):
            repo.set_item(item["id"], state="failed", reason="unsafe_path")
            self._event(repo, item, "intake.failed", "unsafe_path")
        else:
            path = f"{item['storage_key']}/incoming/{item['original_name']}"
            destination = f"{item['storage_key']}/processing/{item['id']}.pdf"
            repo.make_move(item["id"], path, destination, item["fingerprint"], "validating")

    def _finish(self, repo: Repository, item: Record, state: str, reason: str) -> None:
        # Source fingerprint still identifies the exact original bytes after a same-volume rename.
        area = "skipped" if state == "skipped" else "failed"
        destination = f"{item['storage_key']}/{area}/{item['id']}.pdf"
        repo.make_move(
            item["id"], item["relative_path"], destination, item["fingerprint"], state, reason
        )
        self._event(repo, item, "intake." + state, reason)

    def _validate(self, item: Record) -> None:
        try:
            with self.storage.read_guard(item["relative_path"]):
                code = document_code(item["original_name"])
                with self.uow() as repo:
                    repo.set_item(item["id"], code=code)
                    duplicate = repo.code_exists(code)
                if duplicate:
                    with self.uow() as repo:
                        repo.lock_security_state()
                        self._finish(repo, item, "skipped", "duplicate_code")
                    return
                size, sha, proof = self.storage.inspect(item["relative_path"])
                if proof != item["fingerprint"]:
                    raise IntakeFault("changed")
                with self.uow() as repo:
                    repo.set_item(item["id"], size_bytes=size, sha256=sha)
                pages = self.validate(item["relative_path"])
                if self.storage.inspect(item["relative_path"])[:2] != (size, sha):
                    raise IntakeFault("changed")
                with self.uow() as repo:
                    repo.lock_security_state()
                    if not self._allowed(repo, item):
                        self._finish(repo, item, "failed", "access_revoked")
                    elif not repo.admit(item, code, PdfFacts(size, sha, pages)):
                        self._finish(repo, item, "skipped", "duplicate_code")
                    else:
                        self._event(repo, item, "intake.admitted")
                        # The new document itself is excluded by counting another matching code.
                        if repo.same_content(sha, item["fonds_id"]):
                            self._event(repo, item, "intake.warning", "same_content")
        except IntakeFault as exc:
            reason = str(exc)
            with self.uow() as repo:
                repo.lock_security_state()
                if reason == "busy":
                    repo.set_item(item["id"], reason=reason)
                elif reason in {"changed", "unsafe_path", "storage_unavailable"}:
                    repo.set_item(item["id"], state="failed", reason=reason)
                    self._event(repo, item, "intake.failed", reason)
                else:
                    self._finish(repo, item, "failed", reason)
        except OSError:
            with self.uow() as repo:
                repo.set_item(item["id"], state="failed", reason="storage_unavailable")
                self._event(repo, item, "intake.failed", "storage_unavailable")

    def step(self) -> bool:
        with self.lock() as acquired:
            if not acquired:
                return False
            worked = self.reconcile()
            with self.uow() as repo:
                repo.lock_security_state()
                repo.settle_batches()
                item = repo.next_item()
                if item and item["state"] == "pending":
                    self._claim(repo, item)
                    worked = True
            if item and item["state"] == "validating":
                self._validate(item)
                worked = True
            worked = self.reconcile() or worked
            with self.uow() as repo:
                repo.settle_batches()
                event = repo.claim_outbox()
            if event:
                try:
                    self.publish(event)
                except Exception:
                    with self.uow() as repo:
                        repo.fail_outbox(event["id"])
                else:
                    with self.uow() as repo:
                        repo.confirm_outbox(event["id"])
                worked = True
            return worked
