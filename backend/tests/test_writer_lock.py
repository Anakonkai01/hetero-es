"""Production app factories share one kernel lock per management database."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import pytest
from fastapi.testclient import TestClient
from backend.app import app_from_environment
from backend.server import initialize
from backend.writer_lock import acquire_writer


def deployment(tmp_path,monkeypatch):
    root=tmp_path/'lab'
    initialize(root,{'username':'owner','password':'synthetic-lock-test-password','host':'127.0.0.1',
        'port':8765,'storageDirectory':str(tmp_path/'storage')})
    monkeypatch.setenv('HETEROES_PRIVATE_CONFIG',str(root))
    monkeypatch.delenv('HETEROES_WEB_DIRECTORY',raising=False)
    monkeypatch.delenv('HETEROES_DOWNLOADS_DIRECTORY',raising=False)
    return root


def test_second_factory_for_same_database_is_rejected_and_shutdown_releases_it(tmp_path,monkeypatch):
    root=deployment(tmp_path,monkeypatch)
    with TestClient(app_from_environment()) as client:
        assert client.get('/api/v1/health').status_code==200
        with pytest.raises(RuntimeError,match='already owns'):app_from_environment()
        # A different config folder must not bypass a lock on the same DB.
        alias=tmp_path/'alias';alias.mkdir()
        for name in ['config.json','credentials.json']:(alias/name).write_bytes((root/name).read_bytes())
        monkeypatch.setenv('HETEROES_PRIVATE_CONFIG',str(alias))
        with pytest.raises(RuntimeError,match='already owns'):app_from_environment()
    monkeypatch.setenv('HETEROES_PRIVATE_CONFIG',str(root))
    with TestClient(app_from_environment()) as client:assert client.get('/api/v1/health').status_code==200


def test_factory_failure_releases_lock_before_retry(tmp_path,monkeypatch):
    deployment(tmp_path,monkeypatch)
    monkeypatch.setenv('HETEROES_WEB_DIRECTORY',str(tmp_path/'missing'))
    with pytest.raises(FileNotFoundError):app_from_environment()
    monkeypatch.delenv('HETEROES_WEB_DIRECTORY')
    with TestClient(app_from_environment()) as client:assert client.get('/api/v1/health').status_code==200


def test_kernel_lock_excludes_a_second_process_and_recovers_after_close(tmp_path):
    database=tmp_path/'state'/'product.sqlite'
    handle=acquire_writer(database)
    command=[sys.executable,'-c',"from backend.writer_lock import acquire_writer; import sys; h=acquire_writer(sys.argv[1]); h.close()",str(database)]
    try:
        denied=subprocess.run(command,capture_output=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
        assert denied.returncode!=0 and b'already owns' in denied.stderr
    finally:handle.close()
    accepted=subprocess.run(command,capture_output=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
    assert accepted.returncode==0


def test_shutdown_keeps_lock_until_dispatcher_thread_finishes(tmp_path,monkeypatch):
    deployment(tmp_path,monkeypatch)
    entered=threading.Event();release=threading.Event();completed=threading.Event()
    app=app_from_environment()
    def dispatch(stop):
        entered.set();stop.wait(5);release.wait(5);completed.set()
    monkeypatch.setattr(app.state.store,'dispatch',dispatch)
    def serve():
        with TestClient(app):assert entered.wait(3)
    owner=threading.Thread(target=serve);owner.start()
    try:
        assert entered.wait(3)
        # Wait longer than the previous 2-second join to detect premature release.
        owner.join(timeout=2.2)
        assert owner.is_alive() and not completed.is_set()
        with pytest.raises(RuntimeError,match='already owns'):app_from_environment()
    finally:release.set();owner.join(timeout=5)
    assert not owner.is_alive()
    with TestClient(app_from_environment()) as client:assert client.get('/api/v1/health').status_code==200
