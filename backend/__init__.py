"""CPU product service; use the shared runtime package in a source checkout."""

from pathlib import Path
import sys

_source = Path(__file__).resolve().parents[1] / "runtime" / "src"
if _source.is_dir():
    sys.path.insert(0, str(_source))


def __getattr__(name):
    # Preserve these public instrumentation attributes without keeping flat source-module shims.
    namespaces = {"local_storage": ".storage.local_backend", "study_registry": ".services.study_registry"}
    if name not in namespaces:
        raise AttributeError(name)
    from importlib import import_module

    module = import_module(namespaces[name], __name__)
    globals()[name] = module
    sys.modules[__name__ + "." + name] = module
    return module
