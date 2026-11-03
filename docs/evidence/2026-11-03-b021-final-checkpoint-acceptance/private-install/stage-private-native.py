import base64,json,shlex,subprocess,sys,tarfile,time
from pathlib import Path
root=Path('/home/pc5070ti/projects/heteroes');out=Path(__file__).parent
sys.path.insert(0,str(root))
from acceptance.hosts import SSH,HOSTS,POWERSHELL
inputs=out/'native-private-inputs';inputs.mkdir(exist_ok=False)
s=(root/'.scratch/review-2026-11/B9/check-private-server.py').read_text()
s=s.replace("root=Path('/home/pc5070ti/projects/heteroes');out=Path(__file__).parent","root=Path(__file__).resolve().parent;out=root")
s=s.replace("'private-server-linux'","'private-server-windows'")
s=s.replace("Path('/home/pc5070ti/projects/heteroes/.scratch/review-2026-11/C/b021-accept-local-gpu/package-linux/build/server/linux-unpacked/resources/server/profile.json')","root/'profile.json'")
s=s.replace("profile['platforms']['linux']","profile['platforms']['windows']")
s=s.replace("work/'interpreter/python/bin/python3'","work/'interpreter/python/python.exe'")
s=s.replace("root/'desktop/server/resources/runtime.tar.gz'","root/'runtime.tar.gz'")
s=s.replace("out/'server-wheelhouse/linux'","out/'server-wheelhouse/windows'")
s=s.replace("root/'desktop/server/resources/requirements-linux.txt'","root/'requirements-windows.txt'")
s=s.replace("'platform':'linux'","'platform':'windows'").replace("'installedPinnedCPUWheels':23","'installedPinnedCPUWheels':24")
s=s.replace("with selectors.DefaultSelector() as selector:\n  selector.register(process.stdout,selectors.EVENT_READ)\n  assert selector.select(20),'Private interpreter did not announce HTTP origin'\n metadata=json.loads(process.stdout.readline());origin=metadata.pop('origin')", "import queue,threading\n announced=queue.Queue()\n threading.Thread(target=lambda:announced.put(process.stdout.readline()),daemon=True).start()\n metadata=json.loads(announced.get(timeout=20));origin=metadata.pop('origin')")
import ast
ast.parse(s)
(inputs/'check-private-server.py').write_text(s)
profile=json.loads((Path('/home/pc5070ti/projects/heteroes/.scratch/review-2026-11/C/b021-accept-local-gpu/package-linux/build/server/linux-unpacked/resources/server/profile.json')).read_text());python=profile['platforms']['windows']['python']
archive_path=out/'native-private-inputs.tar.gz'
with tarfile.open(archive_path,'w:gz') as archive:
 for name in ['profile.json','requirements-windows.txt','runtime.tar.gz']:
  archive.add(Path('/home/pc5070ti/projects/heteroes/.scratch/review-2026-11/C/b021-accept-local-gpu/package-linux/build/server/linux-unpacked/resources/server')/name,arcname=name)
 archive.add(inputs/'check-private-server.py',arcname='check-private-server.py')
 archive.add(root/'.scratch/review-2026-11/B9/python-inputs'/python['name'],arcname='python-inputs/'+python['name'])
 for wheel in (root/'.scratch/review-2026-11/B9/server-wheelhouse/windows').glob('*.whl'):archive.add(wheel,arcname='server-wheelhouse/windows/'+wheel.name)
name='private-server-b021-'+time.strftime('%Y%m%d-%H%M%S')
remote_wsl='/mnt/c/Users/Thao Nguyen/.cache/heteroes-accept/'+name
remote_windows='C:\\Users\\Thao Nguyen\\.cache\\heteroes-accept\\'+name
record={'wsl':remote_wsl,'windows':remote_windows,'sourceProfileSha256':__import__('hashlib').sha256((Path('/home/pc5070ti/projects/heteroes/.scratch/review-2026-11/C/b021-accept-local-gpu/package-linux/build/server/linux-unpacked/resources/server/profile.json')).read_bytes()).hexdigest()}
(out/'native-private-location.json').write_text(json.dumps(record,indent=2)+'\n')
command='mkdir -p -- '+shlex.quote(remote_wsl)+' && tar -xzf - -C '+shlex.quote(remote_wsl)
subprocess.run([*SSH,command],input=archive_path.read_bytes(),check=True)
def quote(value):return "'"+value.replace("'","''")+"'"
ps='& '+quote(HOSTS['3060-native'].runtime_python)+' -I '+quote(remote_windows+'\\check-private-server.py')+'; exit $LASTEXITCODE'
command=shlex.quote(POWERSHELL)+' -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(ps.encode('utf-16-le')).decode()
result=subprocess.run([*SSH,command]);print('Native private-server exit code',result.returncode,flush=True)
for name in ['private-server-receipt.json','private-server-check.log','private-server-install.log','private-server-stdout.log','private-server-stderr.log']:
 r=subprocess.run([*SSH,'cat -- '+shlex.quote(remote_wsl+'/'+name)],capture_output=True)
 if r.returncode==0:(out/('native-'+name)).write_bytes(r.stdout)
raise SystemExit(result.returncode)
