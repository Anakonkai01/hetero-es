from pathlib import Path
import sys,subprocess,json,tarfile,hashlib,time,base64,shlex
root=Path('/home/pc5070ti/projects/heteroes');out=Path(__file__).parent
sys.path.insert(0,str(root));from acceptance.hosts import SSH,HOSTS,POWERSHELL
resources=root/'.scratch/review-2026-11/C/b021-accept-local-gpu/package-linux/build/server/linux-unpacked/resources/server'
prior=root/'.scratch/review-2026-11/B9';profile=json.loads((resources/'profile.json').read_text());item=profile['platforms']['windows']['python']
bundle=out/'fresh-native-inputs.tar.gz'
with tarfile.open(bundle,'w:gz') as archive:
 for name in ['profile.json','requirements-windows.txt','runtime.tar.gz']:archive.add(resources/name,arcname=name)
 archive.add(out/'check-private-native.py',arcname='check-private-server.py')
 archive.add(prior/'python-inputs'/item['name'],arcname='python-inputs/'+item['name'])
 for wheel in (prior/'server-wheelhouse/windows').glob('*.whl'):archive.add(wheel,arcname='server-wheelhouse/windows/'+wheel.name)
name='private-server-b021-'+time.strftime('%Y%m%d-%H%M%S')
wsl='/mnt/c/Users/Thao Nguyen/.cache/heteroes-accept/'+name;windows='C:\\Users\\Thao Nguyen\\.cache\\heteroes-accept\\'+name
record={'wsl':wsl,'windows':windows,'sourceProfileSha256':hashlib.sha256((resources/'profile.json').read_bytes()).hexdigest(),'sourceCommit':'243f4175'}
(out/'native-location.json').write_text(json.dumps(record,indent=2)+'\n')
subprocess.run([*SSH,'umask 077; mkdir -p '+shlex.quote(wsl)+' && tar -xzf - -C '+shlex.quote(wsl)],input=bundle.read_bytes(),check=True)
quote=lambda s:"'"+s.replace("'","''")+"'"
ps='& '+quote(HOSTS['3060-native'].runtime_python)+' -I '+quote(windows+'\\check-private-server.py')+'; exit $LASTEXITCODE'
command=shlex.quote(POWERSHELL)+' -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(ps.encode('utf-16-le')).decode()
result=subprocess.run([*SSH,command])
for name in ['private-server-receipt.json','private-server-install.log','private-server-stdout.log','private-server-stderr.log']:
 read=subprocess.run([*SSH,'cat -- '+shlex.quote(wsl+'/'+name)],capture_output=True)
 if read.returncode==0:(out/('native-'+name)).write_bytes(read.stdout)
print('Fresh B-021 native private install exit:',result.returncode)
raise SystemExit(result.returncode)
