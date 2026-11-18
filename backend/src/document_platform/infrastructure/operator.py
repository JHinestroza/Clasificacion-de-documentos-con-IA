"""Native operator identity guard for Windows filesystem writes."""

import ctypes
import os


def operator() -> str:
    if os.name != "nt":
        import getpass

        return getpass.getuser()
    name = ctypes.create_unicode_buffer(257)
    length = ctypes.c_ulong(len(name))
    if (
        not ctypes.windll.advapi32.GetUserNameW(name, ctypes.byref(length))
        or "codex" in name.value.casefold()
    ):
        raise RuntimeError("Run intake under the real Windows operator account")
    return name.value
