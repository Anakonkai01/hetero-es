"""
Run a module or script with the CUDA compiler/disassembler DLLs of this Windows venv on the DLL search path.

Native Windows Python does not search PATH for the DLLs that NVRTC needs; the pip-installed CUDA wheels put them in
site-packages. Usage (on Windows): python native_python.py -m pytest ...  |  python native_python.py script.py ...
"""

import os
from pathlib import Path
import runpy
import sys


def dll_directories():
    site = Path(sys.prefix) / "Lib" / "site-packages"
    return sorted({x.parent for x in site.rglob("nvrtc*.dll")} | {x.parent for x in site.rglob("nvdisasm.exe")})


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("native_python.py is for native Windows only")
    directories = dll_directories()
    handles = [os.add_dll_directory(str(d)) for d in directories]
    os.environ["PATH"] = os.pathsep.join(map(str, directories)) + os.pathsep + os.environ.get("PATH", "")
    os.environ["PYTHONNOUSERSITE"] = "1"
    for entry in reversed(os.environ.get("PYTHONPATH", "").split(os.pathsep)):
        if entry:
            sys.path.insert(0, str(Path(entry).resolve()))
    if sys.argv[1] == "-m":
        sys.argv = [sys.argv[2], *sys.argv[3:]]
        runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)
    else:
        sys.argv = sys.argv[1:]
        runpy.run_path(sys.argv[0], run_name="__main__")
