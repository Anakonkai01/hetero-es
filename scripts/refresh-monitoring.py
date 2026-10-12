#!/usr/bin/env python3
"""Vendor the dependency-free, reviewed Track A collector into CPU Server.

With --check nothing is written: Track A, the vendored copies and provenance.json
are compared and the exit status is 1 if they differ.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

MODULES=('energy.py','host_detail.py','windows_detail.py','power.py','telemetry.py')
SOURCE='src/heteroes/product'


def digest(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(track_a,destination):
 """Differences between Track A, the vendored copies and provenance.json."""
 destination=Path(destination);problems=[]
 try:
  listed=json.loads((destination/'provenance.json').read_text())['files']
 except (OSError,ValueError,KeyError):
  return ['provenance.json is missing or unreadable']
 if set(listed)!=set(MODULES):
  problems.append(f'provenance.json lists {sorted(listed)}, expected {sorted(MODULES)}')
 for name in MODULES:
  source=Path(track_a)/SOURCE/name;copy=destination/name
  if not source.is_file():
   problems.append(f'{name}: missing in Track A');continue
  if not copy.is_file():
   problems.append(f'{name}: not vendored');continue
  if digest(source)!=digest(copy):
   problems.append(f'{name}: vendored copy differs from Track A')
  if listed.get(name)!=digest(copy):
   problems.append(f'{name}: provenance.json hash is stale')
 return problems


def refresh(track_a,destination):
 destination=Path(destination);destination.mkdir(exist_ok=True)
 (destination/'__init__.py').write_text('"""Shared stdlib hardware monitoring; see provenance.json."""\n')
 files={}
 for name in MODULES:
  source=Path(track_a)/SOURCE/name
  shutil.copyfile(source,destination/name)
  files[name]=digest(source)
 (destination/'provenance.json').write_text(json.dumps({'source':'hetero-es-m3-runtime/src/heteroes/product','files':files},indent=2)+'\n')


def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--track-a',type=Path,required=True)
 p.add_argument('--check',action='store_true',help='report differences instead of refreshing')
 a=p.parse_args(argv)
 destination=Path(__file__).resolve().parents[1]/'backend/monitoring'
 if a.check:
  problems=check(a.track_a,destination)
  for problem in problems:
   print(problem,file=sys.stderr)
  print('Vendored monitoring modules match Track A and provenance.json.' if not problems else f'{len(problems)} difference(s) found.')
  return 1 if problems else 0
 refresh(a.track_a,destination)
 print('Refreshed shared stdlib monitoring modules; no GPU framework dependency.')
 return 0


if __name__=='__main__':
 raise SystemExit(main())
