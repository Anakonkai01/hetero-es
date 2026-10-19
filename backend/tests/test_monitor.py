import json
import os
import select
import subprocess
import sys
import pytest


# Shared CPU-only imports are checked in test_shared_runtime.py.
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
