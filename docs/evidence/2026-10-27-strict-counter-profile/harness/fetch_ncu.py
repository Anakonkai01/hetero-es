"""Fetch the pinned official redistribution into scratch; verify NVIDIA's SHA-256 before extraction."""
import hashlib,json,tarfile,time,urllib.request
from pathlib import Path
p=Path('docs/evidence/2026-10-27-strict-counter-profile/raw');d=json.loads((p/'cuda-redistrib-13.2.1.json').read_text())['nsight_compute'];item=d['linux-x86_64']
root=Path('.scratch/codex-20261027-ncu');archive=root/'nsight-compute-2026.1.1.2.tar.xz';url='https://developer.download.nvidia.com/compute/cuda/redist/'+item['relative_path']
sha=hashlib.sha256();size=0;started=time.perf_counter()
with urllib.request.urlopen(url,timeout=60) as source,archive.open('xb') as target:
 while chunk:=source.read(1024*1024):target.write(chunk);sha.update(chunk);size+=len(chunk)
assert sha.hexdigest()==item['sha256'] and size==int(item['size'])
with tarfile.open(archive) as t:t.extractall(root,filter='data')
result={'status':'ok','url':url,'version':d['version'],'archiveBytes':size,'sha256':sha.hexdigest(),'matchesNvidiaRedistributionManifest':True,'seconds':time.perf_counter()-started,'limits':'Private scratch extraction only. No driver/environment installation, GPU profile or performance claim.'}
with (p/'ncu-fetch-01.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result),flush=True)
