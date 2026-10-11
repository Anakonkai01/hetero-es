#!/usr/bin/env python3
"""Prepare immutable local downloads from already built desktop apps; no cloud publish."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages',type=Path,required=True)
    parser.add_argument('--build',required=True)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--volume-uuid',default='10443D1F443D094C')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.build):
        parser.error('Build must contain only letters, numbers, underscores and hyphens')
    if subprocess.check_output(['findmnt','-n','-o','UUID','-T',str(args.packages)],text=True).strip()!=args.volume_uuid:
        raise RuntimeError('The selected installer disk is not mounted')
    repo=Path(__file__).resolve().parents[1]
    receipt=args.receipt or repo/'docs/evidence/2026-10-11-ui/installers.json'
    if receipt.exists() and args.receipt:raise RuntimeError('Existing receipt is never overwritten')
    links=repo/'frontend/public/downloads';links.mkdir(parents=True,exist_ok=True)
    manifest={'version':'0.1.0','build':args.build,'privateTrial':True,
              'nativeWindowsGpuVerified':False,'installers':[],'serverInstallers':[]}
    for kind,product,key in [('worker','HeteroES Worker','installers'),('server','HeteroES Lab Server','serverInstallers')]:
        directory=args.packages/kind
        source=directory/f'{product} Setup 0.1.0.exe'
        windows=directory/f'{product}-0.1.0-{args.build}-Windows.exe'
        if windows.exists():
            if sha(windows)!=sha(source):
                raise RuntimeError('Existing immutable Windows build differs; choose a new build name')
        else:
            shutil.copyfile(source,windows)
        linux=directory/f'{product}-0.1.0-{args.build}-Linux.tar.gz'
        if linux.exists():
            raise RuntimeError('Existing immutable Linux build; choose a new build name')
        with linux.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as archive:
                def normalize(info):
                    info.uid=info.gid=info.mtime=0;info.uname=info.gname=''
                    executable=Path(info.name).name in {'heteroes-'+kind,'chrome-sandbox','chrome_crashpad_handler'}
                    info.mode=0o755 if info.isdir() or executable else 0o644
                    return info
                archive.add(directory/'linux-unpacked',arcname='heteroes-'+kind,filter=normalize)
        for platform,file in [('windows',windows),('linux',linux)]:
            link=links/file.name
            if link.is_symlink() or link.exists():
                if link.resolve()!=file.resolve():
                    raise RuntimeError('Existing download link points to another build')
            else:
                link.symlink_to(file.resolve())
            manifest[key].append({'platform':platform,'name':file.name,'url':'/downloads/'+file.name,
                                 'sha256':sha(file),'sizeBytes':file.stat().st_size})
    target=links/'manifest.json'
    if target.exists():
        shutil.copyfile(target,args.packages/f'previous-manifest-{time.time_ns()}.json')
    encoded=json.dumps(manifest,indent=2)+'\n'
    pending=links/'manifest.pending';pending.write_text(encoded);pending.replace(target)
    receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(encoded)
    print(json.dumps({'build':args.build,'downloads':len(manifest['installers'])+len(manifest['serverInstallers']),'cloudPublish':False}))


if __name__=='__main__':
    main()
