"""Backend uses one CPU-safe runtime source, including in packaged source archives."""

import json
from pathlib import Path
import subprocess
import sys


def test_backend_uses_shared_runtime_without_importing_torch():
    code = """import sys, json
import backend.monitor, backend.study_registry
from heteroes.product.telemetry import TelemetrySampler
from heteroes.study.data import dataset
assert backend.monitor.TelemetrySampler is TelemetrySampler
assert backend.study_registry.dataset is dataset
assert 'torch' not in sys.modules
print(json.dumps({'torchImported': False}))
"""
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def test_server_packager_selects_only_cpu_shared_modules():
    from backend.runtime_sources import shared_sources

    repo = Path(__file__).resolve().parents[2]
    sources = shared_sources(repo)
    names = {name for _, name in sources}
    assert "heteroes/product/telemetry.py" in names
    assert "heteroes/study/models.py" in names
    assert not any(name.endswith("/runner.py") for name in names)
    assert {name for name in names if "/noise/" in name} == {
        "heteroes/noise/__init__.py",
        "heteroes/noise/contracts.py",
    }  # identities only; never NumPy, generators or numerical execution
    assert all(source.is_file() for source, _ in sources)


def _runtime_imports(path, package, top_level_only=False):
    """The `heteroes` names a file imports (absolute and relative imports); with `top_level_only`, only the imports that run
    when the module is imported (a lazy import inside a function belongs to a code path the server does not take)."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in tree.body if top_level_only else ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")[: len(package.split(".")) - node.level + 1]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names = [module] + [f"{module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        found.update(name for name in names if name == "heteroes" or name.startswith("heteroes."))
    return found


def test_the_shared_runtime_subset_holds_every_runtime_module_the_backend_needs():
    # The Lab Server ships only SHARED_MODULES: a backend import of another runtime module works in the repository and
    # fails in the packaged server. Checked over the whole import closure (backend files and the shared modules themselves).
    from backend.runtime_sources import SHARED_MODULES

    repo = Path(__file__).resolve().parents[2]
    root = repo / "runtime/src/heteroes"

    def file_of(module):
        relative = Path(*module.split(".")[1:])
        for candidate in (relative.with_suffix(".py"), relative / "__init__.py"):
            if (root / candidate).is_file():
                return candidate.as_posix()
        return None  # a name imported FROM a module (a function, a constant), not a module

    needed = set()
    for path in (repo / "backend").glob("*.py"):
        needed |= {file_of(m) for m in _runtime_imports(path, "backend")} - {None}
    queue = list(needed)
    while queue:
        name = queue.pop()
        package = "heteroes." + name.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
        if not name.endswith("__init__.py"):
            package = package.rsplit(".", 1)[0]
        for module in _runtime_imports(root / name, package, top_level_only=True):
            found = file_of(module)
            if found and found not in needed:
                needed.add(found)
                queue.append(found)
    assert "catalog.py" in needed  # premise: the scan sees the backend's use of the catalog
    assert needed <= set(SHARED_MODULES), sorted(needed - set(SHARED_MODULES))
