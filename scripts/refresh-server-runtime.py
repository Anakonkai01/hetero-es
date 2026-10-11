#!/usr/bin/env python3
"""Refresh CPU Server source/web while preserving reviewed Python and wheel pins."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def main():
    repo=Path(__file__).resolve().parents[1]
    resources=repo/'desktop/server/resources'
    profile_path=resources/'profile.json'
    profile=json.loads(profile_path.read_text())
    assert profile['profile']=='server-cpu-v1'
    assert (repo/'frontend/dist/index.html').is_file(),'Build the Web UI first'
    sources=[(p,str(p.relative_to(repo))) for p in sorted((repo/'backend').rglob('*.py')) if 'tests' not in p.relative_to(repo/'backend').parts]
    sources += [(repo/'backend/monitoring/provenance.json','backend/monitoring/provenance.json')]
    sources += [(p,'web/'+p.relative_to(repo/'frontend/dist').as_posix())
                for p in sorted((repo/'frontend/dist').rglob('*')) if p.is_file()
                and 'downloads' not in p.relative_to(repo/'frontend/dist').parts]
    target=resources/'runtime.tar.gz'
    with target.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as archive:
            for file,name in sources:
                info=archive.gettarinfo(str(file),name)
                info.uid=info.gid=info.mtime=0;info.uname=info.gname=''
                with file.open('rb') as stream:archive.addfile(info,stream)
    profile['runtimeSha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    profile_path.write_text(json.dumps(profile,indent=2)+'\n')
    shared=repo/'desktop/server/electron/shared';shared.mkdir(parents=True,exist_ok=True)
    for name in ('setup.cjs','download.cjs'):shutil.copyfile(repo/'desktop/worker/electron'/name,shared/name)
    print(json.dumps({'profile':profile['profile'],'runtimeSha256':profile['runtimeSha256'],'pinsPreserved':True}))


if __name__=='__main__':main()
