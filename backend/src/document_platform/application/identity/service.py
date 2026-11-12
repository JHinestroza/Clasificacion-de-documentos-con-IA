"""Identity operations commit state and audit together; denied logins remain recorded."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import UUID, uuid4

from document_platform.application.identity.ports import Passwords, Repository, UnitOfWork
from document_platform.domain.identity.models import (
    PERMISSIONS,
    TOKEN_PATTERN,
    Audit,
    AuthenticationError,
    ConflictError,
    IdentityError,
    PermissionDenied,
    RateLimited,
    Session,
    User,
    csrf_for_token,
    digest,
    normalize_username,
    validate_password,
)

T = TypeVar("T")


@dataclass(frozen=True)
class IdentityPolicy:
    idle_seconds: int = 1800
    absolute_seconds: int = 28800
    login_window_seconds: int = 900
    login_max_attempts: int = 5

    def __post_init__(self) -> None:
        if (
            min(
                self.idle_seconds,
                self.absolute_seconds,
                self.login_window_seconds,
                self.login_max_attempts,
            )
            < 1
            or self.idle_seconds > self.absolute_seconds
        ):
            raise ValueError("Invalid identity policy")


@dataclass(frozen=True)
class LoginResult:
    user: User = field(repr=False)
    token: str = field(repr=False)
    csrf_token: str = field(repr=False)


class IdentityService:
    """One unit of work per action, with serialized security state and no HTTP logic."""

    def __init__(
        self,
        unit_of_work: UnitOfWork,
        passwords: Passwords,
        policy: IdentityPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow = unit_of_work
        self._passwords = passwords
        self.policy = policy or IdentityPolicy()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._dummy_hash = passwords.hash(secrets.token_urlsafe(32))

    def _entry(
        self,
        action: str,
        outcome: str,
        actor: UUID | None = None,
        resource: UUID | None = None,
        reason: str | None = None,
        subject: str | None = None,
    ) -> Audit:
        return Audit(uuid4(), actor, action, resource, outcome, self._clock(), reason, subject)

    def audit_rejection(self, action: str) -> None:
        """Record an HTTP boundary rejection without recording cookies, body or credentials."""
        with self._uow() as repo:
            repo.lock_security_state()
            repo.audit(self._entry(action, "denied", reason="Request security validation failed"))

    def login(self, username: str, password: str, previous_token: str | None = None) -> LoginResult:
        now = self._clock()
        subject = digest(username.casefold())
        pending: IdentityError | None = None
        result: LoginResult | None = None
        with self._uow() as repo:
            repo.lock_security_state()
            failures = repo.failures(
                subject, now - timedelta(seconds=self.policy.login_window_seconds)
            )
            if failures >= self.policy.login_max_attempts:
                pending = RateLimited("Authentication temporarily limited; try again later")
            else:
                try:
                    name = normalize_username(username)
                except IdentityError:
                    name = ""
                user = repo.user_by_name(name) if name else None
                try:
                    valid = self._passwords.verify(
                        user.password_hash if user else self._dummy_hash, password
                    )
                    if not valid or user is None or not user.is_active:
                        pending = AuthenticationError("Invalid credentials")
                    else:
                        token = secrets.token_urlsafe(32)
                        csrf = csrf_for_token(token)
                        session = Session(
                            digest(token),
                            user.id,
                            digest(csrf),
                            now,
                            now,
                            now + timedelta(seconds=self.policy.absolute_seconds),
                        )
                        if previous_token and TOKEN_PATTERN.fullmatch(previous_token):
                            old = repo.session(digest(previous_token))
                            if old and old.revoked_at is None:
                                repo.save_session(replace(old, revoked_at=now))
                        repo.insert_session(session)
                        result = LoginResult(user, token, csrf)
                except RateLimited as exc:
                    pending = exc
            if pending:
                outcome = "throttled" if isinstance(pending, RateLimited) else "denied"
                repo.audit(
                    self._entry(
                        "auth.login", outcome, reason="Authentication rejected", subject=subject
                    )
                )
            else:
                assert result is not None
                repo.audit(self._entry("auth.login", "ok", result.user.id, result.user.id))
        # Raise after commit: failed attempts must survive for rate control and audit.
        if pending:
            raise pending
        assert result is not None
        return result

    def _authenticated(
        self, repo: Repository, token: str, csrf: str | None, require_csrf: bool
    ) -> tuple[User, Session]:
        if not TOKEN_PATTERN.fullmatch(token):
            raise AuthenticationError("Authentication required")
        now = self._clock()
        session = repo.session(digest(token))
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at <= now
            or session.last_seen_at + timedelta(seconds=self.policy.idle_seconds) <= now
        ):
            raise AuthenticationError("Authentication required")
        user = repo.user_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Authentication required")
        if require_csrf and (
            not csrf or not secrets.compare_digest(session.csrf_hash, digest(csrf))
        ):
            raise PermissionDenied("Request security validation failed")
        repo.save_session(replace(session, last_seen_at=now))
        return user, session

    def _run(
        self,
        token: str,
        action: str,
        operation: Callable[[Repository, User, Session], T],
        *,
        csrf: str | None = None,
        mutation: bool = False,
        admin: bool = False,
        permission: str | None = None,
        resource: UUID | None = None,
        reason: str | None = None,
    ) -> T:
        pending: IdentityError | None = None
        actor: User | None = None
        result: T
        with self._uow() as repo:
            repo.lock_security_state()
            try:
                actor, session = self._authenticated(repo, token, csrf, mutation)
                if admin and not actor.is_superuser:
                    raise PermissionDenied("Permission denied")
                if permission and not actor.is_superuser and permission not in actor.permissions:
                    raise PermissionDenied("Permission denied")
                result = operation(repo, actor, session)
            except IdentityError as exc:
                pending = exc
                repo.audit(
                    self._entry(
                        action,
                        "denied",
                        actor.id if actor else None,
                        resource,
                        reason="Request denied",
                    )
                )
            else:
                repo.audit(
                    self._entry(
                        action,
                        "ok",
                        actor.id,
                        resource or (result.id if isinstance(result, User) else actor.id),
                        reason=reason,
                    )
                )
        if pending:
            raise pending
        return result

    def me(self, token: str) -> User:
        return self._run(token, "auth.me", lambda repo, user, session: user)

    def csrf(self, token: str) -> str:
        self.me(token)
        return csrf_for_token(token)

    def logout(self, token: str, csrf: str) -> None:
        def operation(repo: Repository, user: User, session: Session) -> None:
            repo.save_session(replace(session, revoked_at=self._clock()))

        self._run(token, "auth.logout", operation, csrf=csrf, mutation=True)

    def change_password(self, token: str, csrf: str, current: str, new: str) -> None:
        def operation(repo: Repository, user: User, session: Session) -> None:
            validate_password(new)
            if not self._passwords.verify(user.password_hash, current):
                raise AuthenticationError("Invalid credentials")
            encoded = self._passwords.hash(new)
            repo.save_user(replace(user, password_hash=encoded, updated_at=self._clock()))
            repo.revoke_sessions(user.id, self._clock())

        self._run(token, "auth.password", operation, csrf=csrf, mutation=True)

    def list_users(self, token: str, limit: int = 50, offset: int = 0) -> list[User]:
        self._pagination(limit, offset)
        return self._run(
            token,
            "users.list",
            lambda repo, user, session: repo.list_users(limit, offset),
            admin=True,
        )

    def create_user(
        self, token: str, csrf: str, username: str, password: str, is_superuser: bool = False
    ) -> User:
        def operation(repo: Repository, actor: User, session: Session) -> User:
            name = normalize_username(username)
            validate_password(password)
            if repo.user_by_name(name):
                raise ConflictError("Username already exists")
            user = User(
                uuid4(),
                name,
                self._passwords.hash(password),
                True,
                is_superuser,
                self._clock(),
                self._clock(),
            )
            repo.insert_user(user)
            return user

        return self._run(token, "users.create", operation, csrf=csrf, mutation=True, admin=True)

    def set_active(self, token: str, csrf: str, user_id: UUID, active: bool, reason: str) -> User:
        def operation(repo: Repository, actor: User, session: Session) -> User:
            if not 3 <= len(reason.strip()) <= 500:
                raise IdentityError("An administrative reason of 3 to 500 characters is required")
            user = repo.user_by_id(user_id)
            if user is None:
                raise IdentityError("User not found")
            if (
                not active
                and user.is_active
                and user.is_superuser
                and repo.count_superusers(active_only=True) <= 1
            ):
                raise ConflictError("The last active superuser cannot be disabled")
            if active == user.is_active:
                return user
            updated = replace(user, is_active=active, updated_at=self._clock())
            repo.save_user(updated)
            repo.revoke_sessions(user.id, self._clock())
            return updated

        return self._run(
            token,
            "users.active",
            operation,
            csrf=csrf,
            mutation=True,
            admin=True,
            resource=user_id,
            reason=reason,
        )

    def set_permissions(
        self, token: str, csrf: str, user_id: UUID, permissions: frozenset[str], reason: str
    ) -> User:
        def operation(repo: Repository, actor: User, session: Session) -> User:
            if actor.id == user_id:
                raise PermissionDenied("Self-assignment of permissions is not allowed")
            if not permissions <= PERMISSIONS:
                raise IdentityError("Unknown permission")
            if not 3 <= len(reason.strip()) <= 500:
                raise IdentityError("An administrative reason of 3 to 500 characters is required")
            user = repo.user_by_id(user_id)
            if user is None:
                raise IdentityError("User not found")
            if permissions != user.permissions:
                repo.set_permissions(user.id, permissions)
                repo.revoke_sessions(user.id, self._clock())
            return replace(user, permissions=permissions)

        return self._run(
            token,
            "users.permissions",
            operation,
            csrf=csrf,
            mutation=True,
            admin=True,
            resource=user_id,
            reason=reason,
        )

    def permission_catalog(self, token: str) -> list[str]:
        return self._run(token, "permissions.list", lambda repo, user, session: sorted(PERMISSIONS))

    def list_audit(self, token: str, limit: int = 50, offset: int = 0) -> list[Audit]:
        self._pagination(limit, offset)
        return self._run(
            token,
            "audit.list",
            lambda repo, user, session: repo.list_audit(limit, offset),
            permission="audit.read",
        )

    def bootstrap_superuser(self, username: str, password: str) -> User:
        name = normalize_username(username)
        validate_password(password)
        pending: IdentityError | None = None
        result: User | None = None
        with self._uow() as repo:
            repo.lock_security_state()
            if repo.count_superusers(active_only=False) or repo.user_by_name(name):
                pending = ConflictError("Superuser initialization already performed")
                repo.audit(
                    self._entry("users.bootstrap", "denied", reason="Bootstrap already initialized")
                )
            else:
                result = User(
                    uuid4(),
                    name,
                    self._passwords.hash(password),
                    True,
                    True,
                    self._clock(),
                    self._clock(),
                )
                repo.insert_user(result)
                repo.audit(self._entry("users.bootstrap", "ok", result.id, result.id))
        if pending:
            raise pending
        assert result is not None
        return result

    @staticmethod
    def _pagination(limit: int, offset: int) -> None:
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise IdentityError("Invalid pagination")
