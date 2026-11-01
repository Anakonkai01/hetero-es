"""Business imports stay usable without loading the HTTP framework or GPU runtime."""

from pathlib import Path
import subprocess
import sys
import textwrap


def test_service_modules_import_without_fastapi_starlette_or_torch():
    root = Path(__file__).resolve().parents[2]
    code = textwrap.dedent("""
        import importlib
        import importlib.abc
        from pathlib import Path
        import sys

        class NoTransportOrGPU(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'fastapi', 'starlette', 'torch'}:
                    raise AssertionError('Business import reached forbidden dependency: ' + fullname)
                return None

        sys.meta_path.insert(0, NoTransportOrGPU())
        for path in sorted(Path('backend/services').glob('*.py')):
            if path.stem != '__init__':
                importlib.import_module('backend.services.' + path.stem)
        assert not {'fastapi', 'starlette', 'torch'} & set(sys.modules)
    """)
    result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
