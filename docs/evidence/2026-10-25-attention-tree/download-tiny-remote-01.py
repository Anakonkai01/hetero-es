"""Download only pinned public assets and publish each file after exact local-manifest verification."""
import argparse,hashlib,json,shutil,subprocess,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if a.out.exists():p.error('Fresh receipt required')
m=json.loads(a.manifest.read_text());root=Path('/home/thao_nguyen/.cache/heteroes-strict-models-20261025/TinyLlama-1.1B-Chat-v1.0')/m['revision'];r={'status':'running','repo':m['repo'],'revision':m['revision'],'destination':str(root),'files':{},'limits':'Public pinned model assets only; no environment/global or device-state changes. Asset verification is not numerical/hardware acceptance.'};start=time.perf_counter()
try:
 needed=sum(x['bytes']for x in m['files'].values());physical=int(subprocess.check_output(['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive','-Command','(Get-PSDrive C).Free']).strip());r['physicalCFreeBeforeBytes']=physical
 if physical<2*needed+2*1024**3:raise RuntimeError('Insufficient physical system-disk reserve')
 root.mkdir(parents=True,exist_ok=False)
 for name,entry in m['files'].items():
  target=root/name;part=root/(name+'.part-01');url=f'https://huggingface.co/{m["repo"]}/resolve/{m["revision"]}/{name}';digest=hashlib.sha256();count=0;last=0
  with urllib.request.urlopen(url,timeout=30)as response,part.open('xb')as f:
   while data:=response.read(1024**2):
    count+=len(data)
    if count>entry['bytes']:raise RuntimeError('Asset exceeds pinned byte limit')
    f.write(data);digest.update(data)
    if count-last>=256*1024**2:print(json.dumps({'file':name,'receivedBytes':count}),flush=True);last=count
  if count!=entry['bytes']or digest.hexdigest()!=entry['sha256']:raise RuntimeError('Pinned asset identity mismatch')
  part.rename(target);r['files'][name]={'bytes':count,'sha256':digest.hexdigest()};print(json.dumps({'file':name,'verifiedBytes':count}),flush=True)
 r['status']='ok'
except Exception as e:r.update(status='error',errorType=type(e).__name__,httpStatus=getattr(e,'code',None))
r['wallSeconds']=time.perf_counter()-start
with a.out.open('x')as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps({'status':r['status'],'wallSeconds':r['wallSeconds'],'errorType':r.get('errorType'),'httpStatus':r.get('httpStatus')}),flush=True);raise SystemExit(r['status']!='ok')
