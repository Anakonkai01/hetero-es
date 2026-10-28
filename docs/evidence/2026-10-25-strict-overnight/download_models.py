"""Fetch two public, pinned trained Llama-family checkpoints for generality checks; never remote code/pickle."""
import hashlib
import json
from pathlib import Path
import time

from huggingface_hub import HfApi, snapshot_download

out = Path('docs/evidence/2026-10-25-strict-overnight/trained-model-downloads-01.json')
if out.exists():
    raise SystemExit('Receipt exists')
report = {'status': 'running', 'models': [], 'limitations': 'Public checkpoints downloaded for inference only. '
          'No new graph capability, quality, learning or hardware acceptance is implied.'}
started = time.monotonic()
try:
    for repo in ('HuggingFaceTB/SmolLM2-360M-Instruct', 'TinyLlama/TinyLlama-1.1B-Chat-v1.0'):
        info = HfApi().model_info(repo, token=False, files_metadata=True)
        path = Path('.scratch/strict-models-20261025') / repo.replace('/', '--') / info.sha
        print(json.dumps({'repo': repo, 'revision': info.sha, 'state': 'downloading'}), flush=True)
        snapshot_download(repo, revision=info.sha, token=False, local_dir=path,
                          allow_patterns=['*.json', '*.safetensors', 'tokenizer.model', '*.txt', 'README.md', 'LICENSE*'],
                          max_workers=2)
        config = json.loads((path / 'config.json').read_text())
        files = {}
        for file in path.rglob('*'):
            if file.is_file() and '.cache' not in file.relative_to(path).parts:
                h = hashlib.sha256()
                with file.open('rb') as f:
                    for block in iter(lambda: f.read(1024**2), b''):
                        h.update(block)
                files[str(file.relative_to(path))] = {'bytes': file.stat().st_size, 'sha256': h.hexdigest()}
        report['models'].append({'repo': repo, 'revision': info.sha, 'path': str(path), 'config': config, 'files': files})
        print(json.dumps({'repo': repo, 'state': 'downloaded', 'bytes': sum(f['bytes'] for f in files.values())}), flush=True)
    report['status'] = 'ok'
except Exception as exc:
    # HTTP exception strings can contain signed download URLs. Record only the type/status, never URL query data.
    report.update(status='error', errorType=type(exc).__name__,
                  httpStatus=getattr(getattr(exc, 'response', None), 'status_code', None))
report['wallSeconds'] = time.monotonic() - started
with out.open('x') as f:
    json.dump(report, f, indent=2); f.write('\n')
print(json.dumps({'status': report['status'], 'models': len(report['models']), 'errorType': report.get('errorType')}))
raise SystemExit(report['status'] != 'ok')
