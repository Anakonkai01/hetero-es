#!/usr/bin/env python3
"""Build a credential-free CPU release from the current checkout and Vite build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if a.output.exists():raise FileExistsError('Choose a new release output')
    subprocess.run(['npm','run','build'],cwd=root/'frontend',env={**os.environ,'VITE_DATA_SOURCE':'real'},check=True)
    with tempfile.TemporaryDirectory(prefix='heteroes-release-') as temporary:
        stage=Path(temporary)
        for name in ('backend','deploy','scripts','docs'):
            shutil.copytree(root/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','tests','*.pyc','*.sqlite','*.log'))
        shutil.copytree(root/'frontend/dist',stage/'frontend/dist',ignore=shutil.ignore_patterns('downloads'))
        files={str(path.relative_to(stage)):hashlib.sha256(path.read_bytes()).hexdigest() for path in stage.rglob('*') if path.is_file()}
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())
        (stage/'release-manifest.json').write_text(json.dumps({'trackBRevision':revision,'sourceTreeDirty':dirty,'dataSource':'real','files':files},indent=2))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with tarfile.open(a.output,'x:gz') as archive:
            for path in sorted(stage.iterdir()):archive.add(path,arcname=path.name)
    with open(a.output,'rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
    print(json.dumps({'release':str(a.output),'sha256':sha,'credentialFree':True}))


if __name__=='__main__':main()
