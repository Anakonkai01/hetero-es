"""Pin selected/remote runtime source, packaged Worker/shared Server/SDK bytes, and vendor files."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import zipfile

root = Path('docs/evidence/2026-10-25-fast-engine')
source = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('runtime/src').rglob('*.py'))}
ssh = ['ssh','-F','/home/pc5070ti/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=8','thao_nguyen@100.92.20.58']
code = "from pathlib import Path;import hashlib,json;root=Path('/tmp/heteroes-fast-engine-20261025-01/src');print(json.dumps({'runtime/src/'+str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}))"
remote = json.loads(subprocess.check_output(ssh+['python3 -c '+shlex.quote(code)],text=True))
assert remote == source
workspace = Path('.scratch/fast-engine-linux-check-20261025-01/workspace')
packages = {}
for app in ('worker','server'):
    archive = workspace/'desktop'/app/'resources/runtime.tar.gz'
    matches = {}
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if not member.isfile() or 'heteroes' not in parts or not member.name.endswith('.py'):
                continue
            name = 'runtime/src/'+'/'.join(parts[parts.index('heteroes'):])
            assert name in source
            digest = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
            assert digest == source[name], (app,name)
            matches[name] = digest
    assert len(matches) == len(source) if app == 'worker' else len(matches) >= 10
    packages[app] = {'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                     'matchedSourceFiles':len(matches),'sourceHashes':matches}
sdk_files = list((workspace/'frontend/dist/notebooks').glob('*.whl'))
assert len(sdk_files) == 1
matches = {}
with zipfile.ZipFile(sdk_files[0]) as wheel:
    for name in wheel.namelist():
        if name.startswith('heteroes/') and name.endswith('.py'):
            key = 'runtime/src/'+name
            digest = hashlib.sha256(wheel.read(name)).hexdigest()
            assert source[key] == digest
            matches[key] = digest
assert matches == source
packages['serverNotebookSdk'] = {'wheelSha256':hashlib.sha256(sdk_files[0].read_bytes()).hexdigest(),
                                  'matchedSourceFiles':len(matches)}
plan = hashlib.sha256(Path('docs/PLAN-SUA-HUMAN-REVIEW.md').read_bytes()).hexdigest()
assert plan == '4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f'
report = {'commit':subprocess.check_output(['git','rev-parse','c9a37059'],text=True).strip(),
          'sourceHashes':source,'remoteSourceHashesEqual':True,'packages':packages,'planSha256':plan,
          'environmentOverrides':{'HETEROES_GPU_ACCEPTANCE':'1','VLLM_USE_FLASHINFER_SAMPLER':'0',
                                  'VLLM_ENABLE_V1_MULTIPROCESSING':'0'},'vllmSourcePins':{}}
names = ['entrypoints/llm.py','envs.py','model_executor/models/llama.py','model_executor/models/qwen2.py',
         'model_executor/layers/linear.py','v1/sample/ops/topk_topp_sampler.py']
for host,lib in [('local','/home/pc5070ti/projects/heteroes/.scratch/vllm-venv-20261024/lib/python3.12/site-packages/vllm'),
                 ('remote','/home/thao_nguyen/heteroes-vllm-20261024/venv/lib/python3.12/site-packages/vllm')]:
    if host == 'local':
        pins = {n:hashlib.sha256((Path(lib)/n).read_bytes()).hexdigest() for n in names}
    else:
        code = 'from pathlib import Path;import hashlib,json;root=Path('+repr(lib)+');names='+repr(names)+';print(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names}))'
        pins = json.loads(subprocess.check_output(ssh+['python3 -c '+shlex.quote(code)],text=True))
    report['vllmSourcePins'][host] = pins
report['localDriver'] = subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version','--format=csv'],text=True)
report['remoteDriver'] = subprocess.check_output(ssh+['/usr/lib/wsl/lib/nvidia-smi --query-gpu=name,driver_version --format=csv'],text=True)
with (root/'selected-source-01.json').open('x') as f:
    json.dump(report,f,indent=2)
    f.write('\n')
print(json.dumps({'runtimeFiles':len(source),'packageMatches':{k:v['matchedSourceFiles'] for k,v in packages.items()}}))
