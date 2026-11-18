"""Bounded child-only PDF structural probe. Stdout contains only a small public result."""

import ctypes
import json
import os
import sys
from ctypes import wintypes
from threading import Timer

_JOB: int | None = None


def memory_limit(megabytes: int, cpu_seconds: int = 30) -> None:
    """Apply OS memory/CPU bounds before importing or parsing untrusted PDF."""
    global _JOB
    size = megabytes * 1024 * 1024
    if os.name != "nt":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (size, size))  # type: ignore[attr-defined]
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))  # type: ignore[attr-defined]
        return

    class Basic(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_int64),
            ("job_time", ctypes.c_int64),
            ("flags", wintypes.DWORD),
            ("minimum", ctypes.c_size_t),
            ("maximum", ctypes.c_size_t),
            ("active", wintypes.DWORD),
            ("affinity", ctypes.c_size_t),
            ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("r", "w", "o", "rb", "wb", "ob")]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", IO),
            ("process_memory", ctypes.c_size_t),
            ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t),
            ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    value = Extended()
    value.basic.flags = 0x100 | 0x2000 | 0x2  # Memory, kill-on-close and process CPU time
    value.basic.process_time = cpu_seconds * 10_000_000
    value.process_memory = size
    if (
        not handle
        or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(value), ctypes.sizeof(value))
        or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())
    ):
        raise RuntimeError("Cannot enforce parser resource bounds")
    _JOB = handle


def arm_deadline(seconds: int) -> None:
    """Terminate this probe at its own wall deadline, even if its parent exits."""
    timer = Timer(seconds, lambda: os._exit(124))
    timer.daemon = True
    timer.start()


def main() -> int:
    result: dict[str, int | str]
    try:
        seconds = int(sys.argv[4])
        arm_deadline(seconds)
        memory_limit(int(sys.argv[3]), seconds)
        from pypdf import PdfReader

        with open(sys.argv[1], "rb") as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted:
                result = {"reason": "encrypted_pdf"}
            else:
                count = len(reader.pages)
                result = (
                    {"pages": count} if 0 < count <= int(sys.argv[2]) else {"reason": "page_limit"}
                )
    except (MemoryError, RuntimeError):
        result = {"reason": "parser_limit"}
    except Exception:
        result = {"reason": "invalid_pdf"}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
