#!/usr/bin/env python3
"""Vendor the dependency-free, reviewed Track A collector into CPU Server."""
import hashlib
import json
from pathlib import Path
import shutil
import argparse
p=argparse.ArgumentParser();p.add_argument('--track-a',type=Path,required=True)
a=p.parse_args();repo=Path(__file__).resolve().parents[1]
destination=repo/'backend/monitoring';destination.mkdir(exist_ok=True)
(destination/'__init__.py').write_text('"""Shared stdlib hardware monitoring; see provenance.json."""\n')
files={}
for name in ('energy.py','host_detail.py','windows_detail.py','power.py','telemetry.py'):
 source=a.track_a/'src/heteroes/product'/name
 shutil.copyfile(source,destination/name)
 files[name]=hashlib.sha256(source.read_bytes()).hexdigest()
(destination/'provenance.json').write_text(json.dumps({'source':'hetero-es-m3-runtime/src/heteroes/product','files':files},indent=2)+'\n')
print('Refreshed shared stdlib monitoring modules; no GPU framework dependency.')
