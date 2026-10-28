"""Read-only hardlink views of existing remote parent assets; verify every byte against portable manifests."""
import hashlib
import json
import os
from pathlib import Path

root=Path('/home/thao_nguyen/.cache/heteroes-codex-frozen-perf-20261025-01')
models={
 'smol':Path('/home/thao_nguyen/.cache/heteroes-strict-models-20261025/SmolLM2-360M-Instruct/a10cc1512eabd3dde888204e902eca88bddb4951'),
 'tiny':Path('/home/thao_nguyen/.cache/heteroes-strict-models-20261025/TinyLlama-1.1B-Chat-v1.0/fe8a4ea1ffedaf415f4da2f062534de366a451e6'),
 'qwen':Path('/home/thao_nguyen/.local/share/heteroes-c4-cpu/models/7ae557604adf67be50417f59c2c2f167def9a775'),
}
target=root/'models'
target.mkdir(exist_ok=False)
for key,source in models.items():
 data=json.loads((root/'bundles'/key/'manifest.json').read_text())
 view=target/key
 view.mkdir()
 for name,expected in data['parentFiles'].items():
  path=source/name
  with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
  assert digest==expected,(key,name)
  destination=view/name
  destination.parent.mkdir(parents=True,exist_ok=True)
  os.link(path,destination)
 print(key,len(data['parentFiles']),'parent files match',flush=True)
