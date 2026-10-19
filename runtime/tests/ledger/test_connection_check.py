"""Connection checks use a device-scoped compute grant and never request work."""
import io
import json
import urllib.error
import pytest
from heteroes.product.connection import check_worker


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body); self.status=status; self.headers=headers or {}


class Routes:
    def __init__(self, private=True, public=True, bulk=True):
        self.calls=[]; self.private=private; self.public=public; self.bulk=bulk

    def open(self, request, timeout):
        self.calls.append(request)
        assert timeout <= 4
        assert request.get_header('Authorization') == 'Bearer compute-secret'
        assert request.get_header('User-agent').startswith('HeteroES-Worker/')
        assert request.get_method() == 'GET'
        if ('100.64.0.1' in request.full_url and not self.private) or ('public.example.org' in request.full_url and not self.public):
            raise urllib.error.URLError('unreachable https://leak.example.org?token=secret')
        if request.full_url.endswith('/v1/health'): return Response(b'{"ok":true}')
        if request.full_url.endswith('/v1/job'): return Response(json.dumps({'ok':True,'job':{'parent_weights_sha256':'a'*64}}).encode())
        if '/v1/models/' in request.full_url:
            assert request.get_header('Range') == 'bytes=0-63'
            if not self.bulk: raise urllib.error.HTTPError(request.full_url, 403, 'forbidden', {}, None)
            return Response(b'x'*64, 206, {'Content-Range':'bytes 0-63/1000000','Content-Length':'64'})
        raise AssertionError('Unexpected request')


def command():
    return {'assignmentId':'b'*32,'epoch':1,'coordinatorUrl':'http://100.64.0.1:8765','bulkUrl':'http://100.64.0.2:8765',
            'publicComputeUrl':'https://public.example.org','computeToken':'compute-secret'}


def test_private_control_and_bounded_bulk_pass_without_leasing():
    routes=Routes()
    report=check_worker(command(), opener=routes)
    assert report['route']=='private' and report['replayOnly'] is False
    assert [(r['step'],r['status']) for r in report['checks']]==[('coordinator','PASS'),('bulk','PASS')]
    assert len(routes.calls)==3
    assert report['checks'][1]['bytesRead']==64
    assert 'compute-secret' not in json.dumps(report)


def test_public_fallback_is_replay_only_and_never_probes_whole_weights():
    routes=Routes(private=False)
    report=check_worker(command(),opener=routes)
    assert report['route']=='public' and report['replayOnly'] is True
    assert report['checks'][0]['status']=='PASS'
    assert report['checks'][1]=={'step':'bulk','status':'SKIP','code':'REPLAY_ONLY'}
    assert all('/v1/models/' not in r.full_url for r in routes.calls)


def test_unreachable_and_bulk_denial_are_explicit_and_do_not_expose_exceptions():
    report=check_worker(command(),opener=Routes(private=False,public=False))
    assert report['checks'][0]['status']=='FAIL'
    assert report['checks'][1]['status']=='SKIP'
    assert 'secret' not in json.dumps(report) and 'leak.example' not in json.dumps(report)
    report=check_worker(command(),opener=Routes(bulk=False))
    assert report['checks'][0]['status']=='PASS' and report['checks'][1]['status']=='FAIL'


@pytest.mark.parametrize('reply', [Response(b'x'*65,200), Response(b'x'*64,200,{'Content-Range':'bytes 0-63/1000'}), Response(b'x'*64,206,{'Content-Range':'bytes 1-64/1000'}),
    Response(b'x'*63,206,{'Content-Range':'bytes 0-63/1000'}), Response(b'x'*64,206,{'Content-Range':'bytes 0-63/10'})])
def test_bulk_pass_requires_exact_range_and_length(reply):
    routes=Routes(); original=routes.open
    routes.open=lambda req,timeout: reply if '/v1/models/' in req.full_url else original(req,timeout)
    report=check_worker(command(),opener=routes)
    assert report['checks'][1]['status']=='FAIL'


def test_no_active_job_does_not_claim_bulk_is_tested():
    routes=Routes(); original=routes.open
    routes.open=lambda req,timeout: Response(b'{"ok":true,"job":null}') if req.full_url.endswith('/v1/job') else original(req,timeout)
    report=check_worker(command(),opener=routes)
    assert report['checks'][1]=={'step':'bulk','status':'SKIP','code':'NO_PUBLISHED_WEIGHTS'}


def test_actual_http_server_requires_compute_grant_and_returns_only_64_bytes(tmp_path):
    from heteroes.http_transport import CoordinatorServer
    import hashlib
    payload=bytes(range(256))*1024
    sha=hashlib.sha256(payload).hexdigest()
    (tmp_path/f'{sha}.bin').write_bytes(payload)
    class NoWorkAPI:
        def handle(self,*args,**kwargs):raise AssertionError('A diagnostic must not lease work')
    server=CoordinatorServer(NoWorkAPI(),job={'parent_weights_sha256':sha},models_dir=tmp_path,device_tokens={'worker':'compute-secret'})
    server.start()
    try:
        cmd={**command(),'coordinatorUrl':server.url,'bulkUrl':server.url,'publicComputeUrl':None}
        assert [r['status'] for r in check_worker(cmd)['checks']]==['PASS','PASS']
        assert check_worker({**cmd,'computeToken':'wrong'})['checks'][0]['status']=='FAIL'
    finally:server.stop()


def test_probe_does_not_forward_grant_to_a_redirect_target():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302);self.send_header('Location','/credential-leak');self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        cmd={**command(),'coordinatorUrl':f'http://127.0.0.1:{server.server_port}','publicComputeUrl':None}
        assert check_worker(cmd)['checks'][0]['status']=='FAIL'
        assert seen==['/v1/health']
    finally:server.shutdown();server.server_close();thread.join()


def test_bridge_checks_only_unreleased_latest_worker_assignment(tmp_path,monkeypatch):
    from heteroes.product.desktop_bridge import Bridge
    from test_device_agent import agent
    from heteroes.product.files import write_json
    a=agent(tmp_path)
    root=a.root/'workers'/('b'*32)
    for recovery in [0,1]:write_json(root/f'r{recovery}'/'assignment.json',{**command(),'recoveryIndex':recovery})
    bridge=object.__new__(Bridge);bridge.agent=a
    seen=[]
    monkeypatch.setattr('heteroes.product.desktop_bridge.check_worker',lambda c: seen.append(c) or {'checks':[]})
    assert len(bridge.call('check_connection')['assignments'])==1
    assert [c['recoveryIndex'] for c in seen]==[1]
    with a.db() as db:db.execute('INSERT INTO released VALUES (?)',('b'*32,))
    assert bridge.call('check_connection')['assignments']==[]


def test_bridge_limits_network_probes_to_one_assignment_per_request(tmp_path,monkeypatch):
    from heteroes.product.desktop_bridge import Bridge
    from test_device_agent import agent
    from heteroes.product.files import write_json
    a=agent(tmp_path); bridge=object.__new__(Bridge);bridge.agent=a
    for key in ['b'*32,'c'*32]:write_json(a.root/'workers'/key/'r0'/'assignment.json',{**command(),'assignmentId':key})
    calls=[]
    monkeypatch.setattr('heteroes.product.desktop_bridge.check_worker',lambda c:calls.append(c) or {'checks':[]})
    report=bridge.call('check_connection')
    assert len(calls)==1
    assert report['assignments'][1]['checks'][0]['code']=='PROBE_LIMIT'
