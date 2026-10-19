"""Read-only, credential-scoped route diagnostics. Never acquire a lease or load CUDA."""
import json
import re
import urllib.request
from heteroes.http_transport import USER_AGENT


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A probe must not forward a compute grant to another origin.
        return None


def check_worker(command, *, opener=None, timeout=4):
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    headers = {'Authorization': 'Bearer ' + command['computeToken'], 'User-Agent': USER_AGENT}

    def get(origin, path, *, byte_range=False):
        request = urllib.request.Request(origin.rstrip('/') + path,
            headers={**headers, **({'Range': 'bytes=0-63'} if byte_range else {})})
        return opener.open(request, timeout=timeout)

    def document(origin, path):
        with get(origin, path) as response:
            if response.status != 200: raise ValueError('Unexpected response')
            payload = response.read(131073)
            if len(payload) > 131072: raise ValueError('Response too large')
            return json.loads(payload)

    origin = command['coordinatorUrl']
    route = 'private'
    try:
        if document(origin, '/v1/health').get('ok') is not True: raise ValueError('Not healthy')
    except Exception:
        origin = command.get('publicComputeUrl')
        route = 'public'
        try:
            if not origin or document(origin, '/v1/health').get('ok') is not True: raise ValueError('Not healthy')
        except Exception:
            return {'route': None, 'checks': [
                {'step': 'coordinator', 'status': 'FAIL', 'code': 'COORDINATOR_UNREACHABLE'},
                {'step': 'bulk', 'status': 'SKIP', 'code': 'CONTROL_REQUIRED'}]}

    checks = [{'step': 'coordinator', 'status': 'PASS', 'code': 'CONTROL_REACHABLE'}]
    report = {'route': route, 'replayOnly': route == 'public', 'checks': checks}
    if route == 'public':
        checks.append({'step': 'bulk', 'status': 'SKIP', 'code': 'REPLAY_ONLY'})
        return report
    try:
        job = document(origin, '/v1/job').get('job') or {}
        parent = job.get('parent_weights_sha256')
        if not isinstance(parent, str) or not re.fullmatch('[a-f0-9]{64}', parent):
            checks.append({'step': 'bulk', 'status': 'SKIP', 'code': 'NO_PUBLISHED_WEIGHTS'})
            return report
        with get(command.get('bulkUrl') or origin, '/v1/models/' + parent, byte_range=True) as response:
            content_range = re.fullmatch(r'bytes 0-63/(\d+)', response.headers.get('Content-Range', ''))
            if response.status != 206 or not content_range or int(content_range.group(1)) < 64:
                raise ValueError('Range not honoured')
            data = response.read(65)
            if len(data) != 64: raise ValueError('Range length mismatch')
        checks.append({'step': 'bulk', 'status': 'PASS', 'code': 'BULK_REACHABLE', 'bytesRead': len(data)})
    except Exception:
        checks.append({'step': 'bulk', 'status': 'FAIL', 'code': 'BULK_CHECK_FAILED'})
    return report
