#!/usr/bin/env python3
"""Expose only the private installer files on the existing local web preview."""
import hashlib,json,pathlib,tarfile
root=pathlib.Path(__file__).resolve().parents[1];release=root/'desktop/worker/release';public=root/'frontend/public/downloads';public.mkdir(parents=True,exist_ok=True)
portable=release/'HeteroES Worker-0.1.0-Linux.tar.gz'
with tarfile.open(portable,'w:gz') as archive:archive.add(release/'linux-unpacked',arcname='HeteroES-Worker')
items=[]
for platform,name in [('windows','HeteroES Worker Setup 0.1.0.exe'),('linux','HeteroES Worker-0.1.0-Linux.tar.gz'),('linux-appimage','HeteroES Worker-0.1.0.AppImage')]:
    file=release/name
    if not file.is_file():raise FileNotFoundError(file)
    sha=hashlib.sha256()
    with file.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):sha.update(data)
    link=public/name
    if link.is_symlink():link.unlink()
    elif link.exists():raise FileExistsError('Refuse to replace a regular file')
    link.symlink_to(pathlib.Path('../../..')/'desktop/worker/release'/name)
    items.append({'platform':platform,'name':name,'url':'/downloads/'+name,'sha256':sha.hexdigest(),'sizeBytes':file.stat().st_size})
manifest={'version':'0.1.0','privateTrial':True,'nativeWindowsGpuVerified':False,'installers':items}
(public/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(root/'docs/evidence/2026-10-10-m3/installers.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('PASS private download links and SHA-256 manifest')
