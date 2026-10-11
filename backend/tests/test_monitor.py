import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import pytest


def test_vendored_collector_provenance_matches_files():
    root=Path(__file__).parents[1]/'monitoring'
    provenance=json.loads((root/'provenance.json').read_text())
    assert set(provenance['files'])=={'energy.py','host_detail.py','power.py','telemetry.py'}
    for file,digest in provenance['files'].items():
        assert hashlib.sha256((root/file).read_bytes()).hexdigest()==digest


@pytest.mark.skipif(sys.platform!='linux',reason='Linux host detail contract')
def test_private_monitor_reports_real_detail_and_exits_on_parent_eof(tmp_path):
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONNOUSERSITE='1')
    child=subprocess.Popen([sys.executable,'-m','backend.monitor','--state',str(tmp_path/'monitor'),'--energy-state',str(tmp_path/'energy')],
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    try:
        assert select.select([child.stdout],[],[],15)[0]
        row=json.loads(child.stdout.readline())
        assert row['observation']['host']['cores']
        assert row['observation']['power']['hostId']
        assert row['history']
        child.stdin.close();child.wait(timeout=8)
        assert child.returncode==0
    finally:
        if child.poll() is None:child.terminate();child.wait(timeout=8)
