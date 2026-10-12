#!/usr/bin/env python3
"""Verify every CPU release file before installing. Standard library only."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root=Path(root).resolve()
    manifest=json.loads((root/'release-manifest.json').read_text())
    expected=manifest['files']
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='release-manifest.json'}
    if actual!=set(expected):raise ValueError('Release file set differs from its manifest')
    for name,wanted in expected.items():
        path=root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Unsafe release path')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=wanted:raise ValueError('Release checksum mismatch: '+name)
    return len(expected)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    args=parser.parse_args();print('Verified',verify(args.directory),'release files')
