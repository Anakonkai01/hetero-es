"""Print one live-lab pairing code for the admin account (password from HETEROES_ADMIN_PASSWORD or a prompt; never stored here), for piping straight into `join`."""
import getpass, json, os, urllib.request
B, H = "https://lab.heteroes.site/api/v1", {"Content-Type": "application/json", "User-Agent": "HeteroES-flagday/1"}
def call(path, body=None, token=None):
    h = dict(H, **({"Authorization": "Bearer " + token} if token else {}))
    with urllib.request.urlopen(urllib.request.Request(B + path, data=json.dumps(body or {}).encode(), headers=h), timeout=60) as r:
        raw = r.read(); return json.loads(raw) if raw else None
token = call("/auth/login", {"username": "admin", "password": os.environ.get("HETEROES_ADMIN_PASSWORD") or getpass.getpass("admin password: ")})["accessToken"]
print(call("/devices/pairing-codes", token=token)["code"])
call("/auth/logout", token=token)
