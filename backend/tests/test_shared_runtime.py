"""Backend uses one CPU-safe runtime source, including in packaged source archives."""
import json
from pathlib import Path
import subprocess
import sys


def test_backend_uses_shared_runtime_without_importing_torch():
    code = '''import sys, json
import backend.monitor, backend.study_registry
from heteroes.product.telemetry import TelemetrySampler
from heteroes.study.data import dataset
assert backend.monitor.TelemetrySampler is TelemetrySampler
assert backend.study_registry.dataset is dataset
assert 'torch' not in sys.modules
print(json.dumps({'torchImported': False}))
'''
    subprocess.run([sys.executable, '-c', code], check=True, capture_output=True)


def test_server_packager_selects_only_cpu_shared_modules():
    from backend.runtime_sources import shared_sources
    repo = Path(__file__).resolve().parents[2]
    sources = shared_sources(repo)
    names = {name for _, name in sources}
    assert 'heteroes/product/telemetry.py' in names
    assert 'heteroes/study/models.py' in names
    assert not any(name.endswith('/runner.py') or '/noise/' in name for name in names)
    assert all(source.is_file() for source, _ in sources)
