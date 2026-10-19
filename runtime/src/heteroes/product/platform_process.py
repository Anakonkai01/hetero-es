"""OS lifecycle primitives. An unreadable process identity is unknown, never dead."""

import os
from pathlib import Path
import sys


class ProcessIdentityUnknown(RuntimeError):
    pass


def identity(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError("Invalid process identifier")
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise ProcessIdentityUnknown("Windows process identity cannot be queried")
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ProcessIdentityUnknown("Windows process state cannot be queried")
            if code.value != 259:
                return None
            values = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
                raise ProcessIdentityUnknown("Windows process birth cannot be queried")
            return "win:" + str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        tail = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if tail[0] == "Z" else tail[19]
    except (FileNotFoundError, ProcessLookupError):
        return None
    except (PermissionError, OSError) as error:
        raise ProcessIdentityUnknown("Linux process identity cannot be queried") from error


def acquire_instance_lock(path):
    """Return an open kernel-locked file; closing it releases the lock on either OS."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    stream = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except Exception:
        stream.close()
        raise


def spawn_options():
    if sys.platform == "win32":
        import subprocess

        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def stop_matches(path, pid=None, birth=None):
    """A durable stop request is bound to the original process, not a reused PID."""
    import json

    pid = os.getpid() if pid is None else pid
    birth = identity(pid) if birth is None else birth
    try:
        value = json.loads(Path(path).read_text())
        return birth is not None and value == {"pid": pid, "birth": birth}
    except (FileNotFoundError, ValueError, OSError):
        return False
