import json, pathlib, sys, urllib.request
s = json.loads((pathlib.Path.home() / '.config/heteroes-demo/session.json').read_text())
tok = s.get('accessToken') or s.get('token') or s.get('session', {}).get('accessToken')
base = sys.argv[1] if len(sys.argv) > 1 else 'http://100.110.165.40:8002'
req = urllib.request.Request(base + (sys.argv[2] if len(sys.argv) > 2 else '/api/v1/devices'), headers={'Authorization': 'Bearer ' + tok, 'User-Agent': 'HeteroES-Worker/0.1'})
rows = json.load(urllib.request.urlopen(req, timeout=20))
keep = ('displayName', 'workerId', 'approvalStatus', 'connectionStatus', 'contributionEnabled', 'contributionDesired',
        'keepContributionAfterReboot', 'allocatedTo', 'stopReason', 'bootId')
print(json.dumps([{k: r.get(k) for k in keep} for r in rows], indent=1))
