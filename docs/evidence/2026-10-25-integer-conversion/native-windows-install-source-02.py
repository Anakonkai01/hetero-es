"""Install the reviewed public wheel resolution into ONLY the task-owned native venv, with exact hashes."""
import hashlib,json,shutil,subprocess,sys,time,urllib.parse
from pathlib import Path
assert sys.platform=='win32'
root=Path.home()/'.cache'/'heteroes-native-strict-20261025-01'
assert Path(sys.prefix).resolve()==(root/'venv').resolve()
if (root/'install-02.json').exists():raise RuntimeError('Fresh install receipt required')
report={'status':'running','root':str(root),'python':sys.executable,'scope':'Task-owned isolated venv; public pinned wheels only; no global/AI environment, GPU or device/lab configuration changes.'}
started=time.perf_counter()
try:
 report['freeBytesBefore']=shutil.disk_usage(root).free
 if report['freeBytesBefore']<14*1024**3:raise RuntimeError('Insufficient reserve for isolated native environment')
 selected={}
 for kind in ('torch','support'):
  resolution=json.loads((root/('resolve-'+kind+'-01.json')).read_text(encoding='utf-8-sig'))
  for item in resolution['install']:
   info=item['download_info'];url=info['url'];parsed=urllib.parse.urlparse(url)
   if parsed.scheme!='https' or parsed.hostname not in ('download.pytorch.org','download-r2.pytorch.org','files.pythonhosted.org'):raise RuntimeError('Unexpected wheel source')
   if not parsed.path.endswith('.whl'):raise RuntimeError('Binary wheel required')
   name=item['metadata']['name'].lower().replace('_','-')
   selected[name]={'name':item['metadata']['name'],'version':item['metadata']['version'],'url':url,'sha256':info['archive_info']['hashes']['sha256']}
 locked=root/'install-wheels-02.txt'
 with locked.open('x',encoding='utf-8')as f:
  for name,item in sorted(selected.items()):f.write(item['url']+'#sha256='+item['sha256']+'\n')
 report['wheels']=list(selected.values());report['lockSha256']=hashlib.sha256(locked.read_bytes()).hexdigest()
 cmd=[sys.executable,'-I','-B','-m','pip','--isolated','install','--no-deps','--only-binary=:all:','--require-hashes','--no-cache-dir','--progress-bar','off','--index-url','https://pypi.org/simple','--report',str(root/'pip-install-02.json'),'-r',str(locked)]
 result=subprocess.run(cmd);report['pipExitCode']=result.returncode
 if result.returncode:raise RuntimeError('Pinned native installation failed')
 check=subprocess.run([sys.executable,'-I','-B','-m','pip','--isolated','check']);report['pipCheckExitCode']=check.returncode
 if check.returncode:raise RuntimeError('Native dependency check failed')
 report['freeBytesAfter']=shutil.disk_usage(root).free
 report['status']='ok'
except Exception as exc:report.update(status='error',errorType=type(exc).__name__,error=str(exc))
report['wallSeconds']=time.perf_counter()-started
with (root/'install-02.json').open('x')as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({'status':report['status'],'wallSeconds':report['wallSeconds'],'error':report.get('error')}));raise SystemExit(report['status']!='ok')
