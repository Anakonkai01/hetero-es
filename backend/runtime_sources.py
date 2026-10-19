"""Exact CPU-only runtime subset shipped with the Lab Server."""

from pathlib import Path

SHARED_MODULES = (
    "__init__.py",
    "catalog.py",
    "canonical.py",
    "recovery_manifest.py",
    "v3/__init__.py",
    "v3/data.py",
    "v3/options.py",
    "v3/scoring.py",
    "product/__init__.py",
    "product/energy.py",
    "product/host_detail.py",
    "product/windows_detail.py",
    "product/power.py",
    "product/telemetry.py",
    "study/__init__.py",
    "study/data.py",
    "study/models.py",
)


def shared_sources(repo):
    root = Path(repo) / "runtime/src/heteroes"
    return [(root / name, "heteroes/" + name) for name in SHARED_MODULES]
