"""An old server accepts the unchanged Poll body and ignores the new header."""
import json
from heteroes.product.agent import request, COMMAND_KINDS


def test_agent_advertises_command_kinds_only_in_poll_header(monkeypatch):
    import io
    seen=[]
    def open(req,timeout):
        seen.append(req)
        return io.BytesIO(b'{"ok":true}')
    monkeypatch.setattr('urllib.request.urlopen',open)
    body={'bootId':'boot','contribution':False,'processes':[],'reports':[]}
    request('https://lab.example.org','/api/v1/device/poll','synthetic-token',body)
    assert json.loads(seen[0].data)==body
    advertised=seen[0].get_header('X-heteroes-agent-commands')
    assert set(advertised.split(','))==COMMAND_KINDS
    assert 'CANCEL_ASSIGNMENT' in advertised and 'PAUSE_ASSIGNMENT' in advertised
    request('https://lab.example.org','/api/v1/device/worker-command','synthetic-token',{})
    assert seen[1].get_header('X-heteroes-agent-commands') is None
