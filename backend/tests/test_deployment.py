import json
import os
import subprocess
import socket
import time
import urllib.request
import pytest
from backend.deployment import caddyfile, idle, save_private
from backend.server import initialize


def test_entrypoints_do_not_select_private_bulk_by_host_header():
    text=caddyfile({'apiUrl':'http://100.64.0.1:8002','privateComputeUrl':'http://100.64.0.1:8765'})
    assert 'http://:8080' in text and 'http://:8081' in text and text.count('bind 127.0.0.1')==2
    assert 'admin off' in text and '/v1/models/' not in text
    assert '/api/v1/local-storage/*' in text and '403' in text
    with pytest.raises(ValueError):
        caddyfile({'apiUrl':'https://public.example.org','privateComputeUrl':'http://100.64.0.1:8765'})
    with pytest.raises(ValueError):
        caddyfile({'apiUrl':'http://100.64.0.1:8002','privateComputeUrl':'http://100.64.0.1:8765','webEntryPort':8081})


def test_private_config_and_idle_guard(tmp_path):
    root=tmp_path/'private'
    initialize(root,{'username':'admin','password':'test-password-long','host':'127.0.0.1','port':8002,'storageDirectory':str(tmp_path/'objects')})
    path=root/'config.json'
    config=json.loads(path.read_text())
    idle(config)
    save_private(path,{**config,'publicWebUrl':'https://example.trycloudflare.com'})
    assert os.stat(path).st_mode & 0o777 == 0o600
    import sqlite3
    with sqlite3.connect(root/'state/product.sqlite') as db:
        db.execute("UPDATE settings SET value='false' WHERE key='dispatchHold'")
    with pytest.raises(RuntimeError,match='Hold dispatch'):
        idle(config)


def test_real_proxy_accepts_tunnel_host_and_denies_bulk_even_with_forged_host(tmp_path):
    from pathlib import Path
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    binary=Path.home()/'.local/share/heteroes-tools/caddy'
    if not binary.is_file():pytest.skip('Caddy executable unavailable')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=b'{"ok":true}'
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=upstream.serve_forever,daemon=True);thread.start()
    def port():
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
    web,compute=port(),port()
    config={'apiUrl':f'http://127.0.0.1:{upstream.server_port}','privateComputeUrl':f'http://127.0.0.1:{upstream.server_port}','webEntryPort':web,'computeEntryPort':compute}
    file=tmp_path/'Caddyfile';file.write_text(caddyfile(config))
    process=subprocess.Popen([str(binary),'run','--config',str(file)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline=time.monotonic()+10
        while True:
            try:
                response=opener.open(urllib.request.Request(f'http://127.0.0.1:{web}/api/v1/health',headers={'Host':'example.trycloudflare.com'}),timeout=1)
                assert json.load(response)=={'ok':True}
                break
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        for p,path in [(web,'/api/v1/local-storage/object'),(web,'/downloads/worker.exe'),(compute,'/v1/models/'+'a'*64)]:
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(urllib.request.Request(f'http://127.0.0.1:{p}'+path,headers={'Host':'127.0.0.1'}),timeout=2)
            assert error.value.code==403
    finally:
        process.terminate();process.wait(timeout=10);upstream.shutdown();upstream.server_close()
