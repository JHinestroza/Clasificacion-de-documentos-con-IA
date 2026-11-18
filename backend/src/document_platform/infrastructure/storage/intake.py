"""Private single-volume storage with no-replace moves and restart reconciliation."""

import ctypes
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

from document_platform.domain.ingestion.models import CODE, IntakeFault, Record, document_code
from document_platform.infrastructure.operator import operator

AREAS = ("incoming", "processing", "failed", "success", "skipped")


def fingerprint(path: Path) -> dict[str, int]:
    value = path.lstat()
    if not stat.S_ISREG(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
        raise IntakeFault("unsafe_path")
    return {
        "dev": value.st_dev,
        "ino": value.st_ino,
        "size": value.st_size,
        "mtime": value.st_mtime_ns,
    }


def safe_parents(path: Path) -> None:
    for p in (path, *path.parents):
        if p.exists() or p.is_symlink():
            s = p.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise IntakeFault("unsafe_path")


def publish_file(source: Path, destination: Path) -> None:
    """Publish without replacement; interrupted POSIX hard-link publication is recoverable."""
    if os.name == "nt":
        source.rename(destination)
    else:
        os.link(source, destination, follow_symlinks=False)
        source.unlink()


class IntakeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        safe_parents(self.root)

    def path(self, relative: str) -> Path:
        parts = relative.split("/")
        if len(parts) != 3 or CODE.fullmatch(parts[0]) is None or parts[1] not in AREAS:
            raise IntakeFault("unsafe_path")
        if not parts[2] or parts[2] in (".", "..") or any(c in parts[2] for c in "/\\:\0"):
            raise IntakeFault("unsafe_path")
        target = self.root.joinpath(*parts)
        safe_parents(target)
        return target

    def ensure(self, key: str) -> None:
        operator()
        if CODE.fullmatch(key) is None or key != key.upper():
            raise IntakeFault("unsafe_path")
        safe_parents(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        device = self.root.stat().st_dev
        for area in AREAS:
            folder = self.root / key / area
            safe_parents(folder)
            folder.mkdir(parents=True, exist_ok=True)
            if folder.stat().st_dev != device:
                raise IntakeFault("unsafe_path")

    def candidates(self, key: str, limit: int) -> list[Record]:
        folder = self.root / key / "incoming"
        safe_parents(folder)
        rows: list[Record] = []
        for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not path.name.lower().endswith(".pdf"):
                continue
            if len(rows) >= limit:
                raise IntakeFault("batch_limit")
            try:
                proof = fingerprint(path)
            except IntakeFault:
                # Record unsafe candidates without following or moving their target.
                proof = {"unsafe": 1}
            rows.append({"name": path.name, "fingerprint": proof})
        return rows

    def complete_move(self, source: str, destination: str, proof: dict[str, int]) -> None:
        src, dst = self.path(source), self.path(destination)
        source_exists = src.exists()
        dest_exists = dst.exists()
        if dest_exists:
            if fingerprint(dst) != proof:
                raise IntakeFault("move_conflict")
            if source_exists:
                if fingerprint(src) != proof or not os.path.samefile(src, dst):
                    raise IntakeFault("move_conflict")
                src.unlink()  # Finish only the journaled POSIX link/unlink operation.
            return
        if not source_exists:
            raise IntakeFault("storage_unavailable")
        if fingerprint(src) != proof:
            raise IntakeFault("changed")
        if src.stat().st_dev != dst.parent.stat().st_dev:
            raise IntakeFault("unsafe_path")
        try:
            publish_file(src, dst)
        except FileExistsError:
            raise IntakeFault("move_conflict") from None
        except PermissionError:
            raise IntakeFault("busy") from None
        if fingerprint(dst) != proof:
            raise IntakeFault("changed")

    @contextmanager
    def read_guard(self, relative: str) -> Iterator[None]:
        """Deny concurrent writers during hashing/parsing, permitting readers and rename."""
        path = self.path(relative)
        fingerprint(path)
        if os.name != "nt":
            with path.open("rb"):
                yield
            return
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(path), 0x80000000, 0x1 | 0x4, None, 3, 0x200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise IntakeFault(
                "busy" if ctypes.get_last_error() in (32, 33) else "storage_unavailable"
            )
        try:
            yield
        finally:
            kernel.CloseHandle(handle)

    def inspect(self, relative: str) -> tuple[int, str, dict[str, int]]:
        path = self.path(relative)
        before = fingerprint(path)
        if before["size"] > 100_000_000:
            raise IntakeFault("too_large")
        if before["size"] == 0:
            raise IntakeFault("invalid_pdf")
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        if fingerprint(path) != before:
            raise IntakeFault("changed")
        return before["size"], sha.hexdigest(), before

    def deposit(self, source: Path, key: str) -> Path:
        """Copy an operator-selected complete PDF, then publish .part -> .pdf atomically.

        The source outside the managed inbox is preserved. Interrupted .part files
        remain private for diagnosis; they are never selected by a batch.
        """
        document_code(source.name)
        safe_parents(source.absolute())
        proof = fingerprint(source)
        if not 0 < proof["size"] <= 100_000_000:
            raise IntakeFault("too_large")
        self.ensure(key)
        destination = self.path(f"{key}/incoming/{source.name}")
        if destination.exists():
            raise IntakeFault("move_conflict")
        partial = destination.with_name(uuid4().hex + ".part")
        sha = hashlib.sha256()
        with source.open("rb") as src, partial.open("xb") as dst:
            total = 0
            while chunk := src.read(1024 * 1024):
                total += len(chunk)
                if total > 100_000_000:
                    raise IntakeFault("too_large")
                sha.update(chunk)
                dst.write(chunk)
            dst.flush()
            os.fsync(dst.fileno())
        if fingerprint(source) != proof or total != proof["size"]:
            raise IntakeFault("changed")
        with partial.open("rb") as staged:
            if hashlib.file_digest(staged, "sha256").hexdigest() != sha.hexdigest():
                raise IntakeFault("changed")
        publish_file(partial, destination)
        return destination
