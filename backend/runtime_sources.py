"""Exact CPU-only runtime subset shipped with the Lab Server."""
from pathlib import Path

SHARED_MODULES = (
    '__init__.py', 'product/__init__.py', 'product/energy.py', 'product/host_detail.py',
    'product/windows_detail.py', 'product/power.py', 'product/telemetry.py',
    'study/__init__.py', 'study/data.py', 'study/models.py',
)


def shared_sources(repo):
    root = Path(repo) / 'runtime/src/heteroes'
    return [(root / name, 'heteroes/' + name) for name in SHARED_MODULES]
