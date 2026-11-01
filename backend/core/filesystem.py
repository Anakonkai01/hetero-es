"""Atomic filesystem publication helpers."""

import ctypes
import os
import sys


def publish_new_directory(staging, destination):
    if sys.platform.startswith("linux"):
        # os.rename can replace an empty directory created between verification
        # and publication. Linux RENAME_NOREPLACE closes that race atomically.
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        # Windows rename already refuses an existing destination directory.
        staging.rename(destination)
