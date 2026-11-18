"""Authorized intake commands: action, resource scope, state and audit commit together."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from document_platform.application.identity.service import IdentityService
from document_platform.application.ingestion.ports import Repository, Storage, UnitOfWork
from document_platform.domain.identity.models import (
    Audit,
    ConflictError,
    IdentityError,
    PermissionDenied,
    User,
)
from document_platform.domain.ingestion.models import (
    ACTIVE_BATCHES,
    CODE,
    IntakeFault,
    Record,
    reason_text,
)

MONITOR = frozenset(
    {"documents.read", "failed.read", "processing.start", "processing.pause", "processing.stop"}
)


class IngestionService:
    def __init__(
        self, uow: UnitOfWork, identity: IdentityService, storage: Storage, batch_limit: int
    ) -> None:
        self.uow, self.identity, self.storage, self.batch_limit = (
            uow,
            identity,
            storage,
            batch_limit,
        )

    def _run(
        self,
        token: str,
        action: str,
        operation: Callable[[Repository, User, Record | None], Record | list[Record]],
        *,
        csrf: str | None = None,
        permission: str | None = None,
        admin: bool = False,
        fonds_id: UUID | None = None,
        batch_id: UUID | None = None,
        reason: str | None = None,
        resource_id: UUID | None = None,
    ) -> Record | list[Record]:
        error: IdentityError | None = None
        actor: User | None = None
        scope: UUID | None = None
        result: Record | list[Record]
        with self.uow() as repo:
            repo.lock_security_state()
            try:
                with repo.atomic():
                    actor = self.identity.authorize(
                        repo,
                        token,
                        csrf=csrf,
                        mutation=csrf is not None,
                        permission=permission,
                        admin=admin,
                    )
                    context = (
                        repo.batch(batch_id)
                        if batch_id
                        else repo.fonds(fonds_id)
                        if fonds_id
                        else None
                    )
                    if (batch_id or fonds_id) and context is None:
                        raise PermissionDenied("Resource unavailable")
                    if context:
                        scope = context["fonds_id"] if batch_id else context["id"]
                        if not repo.has_access(actor, scope):
                            raise PermissionDenied("Resource unavailable")
                    if reason is not None and not 3 <= len(reason.strip()) <= 500:
                        raise IdentityError("A reason of 3 to 500 characters is required")
                    result = operation(repo, actor, context)
                    if action == "fonds.create":
                        assert isinstance(result, dict)
                        scope = result["id"]
            except IdentityError as exc:
                error = exc
            except IntakeFault as exc:
                error = IdentityError(reason_text(str(exc)))
            repo.audit(
                Audit(
                    uuid4(),
                    actor.id if actor else None,
                    action,
                    resource_id or batch_id or scope,
                    "denied" if error else "ok",
                    datetime.now(UTC),
                    "Request denied" if error else reason,
                    fonds_id=scope,
                )
            )
        if error:
            raise error
        return result

    @staticmethod
    def _monitor(user: User) -> None:
        if not user.is_superuser and not user.permissions & MONITOR:
            raise PermissionDenied("Permission denied")

    @staticmethod
    def _page(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or not 0 <= offset <= 1000000:
            raise IdentityError("Invalid pagination")

    def fonds(self, token: str) -> list[Record]:
        def operation(repo: Repository, actor: User, ctx: Record | None) -> list[Record]:
            self._monitor(actor)
            rows = repo.list_fonds(actor)
            for row in rows:
                row["incoming_path"] = (
                    str(self.storage.root / row["storage_key"] / "incoming")
                    if actor.is_superuser or "processing.start" in actor.permissions
                    else None
                )
            return rows

        value = self._run(token, "fonds.list", operation)
        assert isinstance(value, list)
        return value

    def create_fonds(self, token: str, csrf: str, name: str, key: str) -> Record:
        def operation(repo: Repository, actor: User, ctx: Record | None) -> Record:
            if (
                not 1 <= len(name.strip()) <= 100
                or not name.isprintable()
                or CODE.fullmatch(key) is None
                or key != key.upper()
            ):
                raise IdentityError("Invalid fonds name or storage key")
            row = repo.create_fonds(name.strip(), key)
            self.storage.ensure(key)
            return row

        value = self._run(token, "fonds.create", operation, csrf=csrf, admin=True)
        assert isinstance(value, dict)
        return value

    def members(self, token: str, fonds_id: UUID) -> list[Record]:
        value = self._run(
            token,
            "fonds.members",
            lambda r, a, c: r.memberships(fonds_id),
            admin=True,
            fonds_id=fonds_id,
        )
        assert isinstance(value, list)
        return value

    def grant(
        self, token: str, csrf: str, fonds_id: UUID, user_id: UUID, enabled: bool, reason: str
    ) -> Record:
        def operation(repo: Repository, actor: User, ctx: Record | None) -> Record:
            user = repo.user_by_id(user_id)
            if user is None:
                raise IdentityError("Account unavailable")
            repo.grant(fonds_id, user_id, enabled)
            return {"user_id": user_id, "enabled": enabled}

        value = self._run(
            token,
            "fonds.grant" if enabled else "fonds.revoke",
            operation,
            csrf=csrf,
            admin=True,
            fonds_id=fonds_id,
            reason=reason,
            resource_id=user_id,
        )
        assert isinstance(value, dict)
        return value

    def start(self, token: str, csrf: str, fonds_id: UUID) -> Record:
        def operation(repo: Repository, actor: User, ctx: Record | None) -> Record:
            assert ctx is not None
            if not ctx["active"]:
                raise ConflictError("Fonds is inactive")
            candidates = self.storage.candidates(ctx["storage_key"], self.batch_limit)
            if not candidates:
                raise ConflictError("There are no complete PDF files in this inbox")
            result = repo.start(fonds_id, actor.id, candidates)
            repo.event(fonds_id, result["id"], None, actor.id, "batch.started")
            return result

        value = self._run(
            token,
            "batch.start",
            operation,
            csrf=csrf,
            permission="processing.start",
            fonds_id=fonds_id,
        )
        assert isinstance(value, dict)
        return value

    def batches(self, token: str, fonds_id: UUID, limit: int, offset: int) -> list[Record]:
        self._page(limit, offset)

        def operation(repo: Repository, actor: User, ctx: Record | None) -> list[Record]:
            self._monitor(actor)
            return repo.batches(fonds_id, limit, offset)

        value = self._run(token, "batch.list", operation, fonds_id=fonds_id)
        assert isinstance(value, list)
        return value

    def detail(self, token: str, batch_id: UUID) -> Record:
        def operation(repo: Repository, actor: User, ctx: Record | None) -> Record:
            self._monitor(actor)
            assert ctx is not None
            return ctx

        value = self._run(token, "batch.detail", operation, batch_id=batch_id)
        assert isinstance(value, dict)
        return value

    def command(self, token: str, csrf: str, batch_id: UUID, command: str, reason: str) -> Record:
        permission = {
            "pause": "processing.pause",
            "resume": "processing.start",
            "stop": "processing.stop",
            "retry-publication": "processing.start",
        }.get(command)
        if permission is None:
            raise IdentityError("Invalid batch command")

        def operation(repo: Repository, actor: User, ctx: Record | None) -> Record:
            assert ctx is not None
            state = ctx["state"]
            if command == "retry-publication":
                repo.retry_outbox(batch_id)
                result = ctx
            else:
                if command == "pause" and state == "running":
                    state = "pause_requested"
                elif command == "stop" and state in ACTIVE_BATCHES:
                    state = "stop_requested"
                elif command == "resume" and state == "paused":
                    state = "running"
                else:
                    raise ConflictError("This batch command is not valid in the current state")
                result = repo.command_batch(
                    batch_id, state, actor.id if command == "resume" else None
                )
            repo.event(ctx["fonds_id"], batch_id, None, actor.id, "batch." + command)
            return result

        value = self._run(
            token,
            "batch." + command,
            operation,
            csrf=csrf,
            permission=permission,
            batch_id=batch_id,
            reason=reason,
        )
        assert isinstance(value, dict)
        return value

    def items(
        self, token: str, batch_id: UUID, limit: int, offset: int, search: str, state: str
    ) -> list[Record]:
        self._page(limit, offset)
        if len(search) > 100 or state not in {
            "",
            "pending",
            "claimed",
            "validating",
            "finishing",
            "admitted",
            "skipped",
            "failed",
            "pending_publish",
            "queued",
        }:
            raise IdentityError("Invalid filter")

        def operation(repo: Repository, actor: User, ctx: Record | None) -> list[Record]:
            effective = state
            if not actor.is_superuser and "documents.read" not in actor.permissions:
                if "failed.read" not in actor.permissions:
                    raise PermissionDenied("Permission denied")
                effective = "failed"
            rows = repo.items(batch_id, limit, offset, search, effective)
            for row in rows:
                row["reason_text"] = reason_text(row["reason"])
            return rows

        value = self._run(token, "intake.list", operation, batch_id=batch_id)
        assert isinstance(value, list)
        return value

    def events(self, token: str, batch_id: UUID, limit: int, offset: int) -> list[Record]:
        self._page(limit, offset)
        value = self._run(
            token,
            "intake.events",
            lambda r, a, c: r.events(batch_id, limit, offset),
            permission="audit.read",
            batch_id=batch_id,
        )
        assert isinstance(value, list)
        return value
