#!/usr/bin/env python3
"""Refresh packaged Track A source without changing pinned installer dependencies."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--track-a', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'desktop/worker/resources'
    target = root / 'runtime.tar.gz'
    sources = list((args.track_a/'src/heteroes').rglob('*.py')) + [args.track_a/'scripts/run_worker.py']
    with target.open('wb') as raw, gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,filename='') as compressed:
        with tarfile.open(fileobj=compressed,mode='w') as archive:
            for file in sorted(sources):
                info = archive.gettarinfo(str(file),str(file.relative_to(args.track_a)))
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                with file.open('rb') as stream:
                    archive.addfile(info,stream)
    profile = json.loads((root/'profile.json').read_text())
    profile['runtimeSha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    (root/'profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    print('Pinned Python/wheels/model preserved; packaged source refreshed:',profile['runtimeSha256'])


if __name__ == '__main__':
    main()
