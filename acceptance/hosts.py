"""
The machines the acceptance checks run on. No credentials here: SSH uses the controller's own ~/.ssh/config and keys.

- local: Nhân's RTX 5070 Ti (SM120), Linux.
- 3060-wsl: Thảo's RTX 3060 (SM86) under WSL2, reached by SSH.
- 3060-native: the same RTX 3060 under native Windows 11, driven from its WSL2 side through PowerShell.
"""

from acceptance.core import Host

LOCAL = Host(
    "local",
    runtime_python="/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python",
    models="/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models",
)

# WSL2: the Windows-provided driver/JIT libraries must come first (the distribution's own segfault in CUDA discovery).
WSL = Host(
    "3060-wsl",
    runtime_python="/home/thao_nguyen/.local/share/heteroes-c4-cpu/runtimes/9a553d2dfae9/python/bin/python3.12",
    models="/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01/models",
    env={"LD_LIBRARY_PATH": "/usr/lib/wsl/drivers/nv_dispi.inf_amd64_feedb8c0271ca811:/usr/lib/wsl/lib"},
    extra_path="/tmp/heteroes-codex-testdeps-20261027-01",  # pytest and friends, outside the runtime
)

NATIVE_ROOT = r"C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01"
NATIVE = Host(
    "3060-native",
    runtime_python=NATIVE_ROOT + r"\venv\Scripts\python.exe",
    models=NATIVE_ROOT + r"\models-prefetch-01",
)

HOSTS = {h.label: h for h in (LOCAL, WSL, NATIVE)}

# How the controller reaches the remote hosts (used by `scripts/accept.py remote`).
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "thao_nguyen@100.92.20.58"]
REMOTE_ROOT = {"3060-wsl": "/tmp", "3060-native": "/mnt/c/Users/Thao Nguyen/.cache/heteroes-accept"}
WINDOWS_ROOT = r"C:\Users\Thao Nguyen\.cache\heteroes-accept"
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
