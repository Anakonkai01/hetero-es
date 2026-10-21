#!/usr/bin/env python3
"""Sign in to the live lab once and keep the session for the notebook and the overnight monitor.

    python3 scripts/lab-login.py [--url https://lab.heteroes.site] [--username admin] [--workspace NAME]

The password is read with a prompt (or HETEROES_ADMIN_PASSWORD) and never written anywhere. The access token (valid 12 hours)
and the workspace id go to ~/.config/heteroes-demo/session.json with mode 0600, outside the repository.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import urllib.request

SESSION = Path.home() / ".config" / "heteroes-demo" / "session.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="https://lab.heteroes.site")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--workspace", help="workspace name (default: the first one of the account)")
    args = parser.parse_args()
    password = os.environ.get("HETEROES_ADMIN_PASSWORD") or getpass.getpass(f"{args.username} password: ")
    request = urllib.request.Request(
        args.url.rstrip("/") + "/api/v1/auth/login",
        data=json.dumps({"username": args.username, "password": password}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "HeteroES-demo/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        session = json.load(response)
    workspaces = session["workspaces"]
    chosen = next((w for w in workspaces if args.workspace in (None, w["name"])), None)
    if chosen is None:
        raise SystemExit(f"No workspace named {args.workspace!r}; have {[w['name'] for w in workspaces]}")
    SESSION.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(SESSION, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"url": args.url.rstrip("/"), "token": session["accessToken"], "workspace": chosen["workspaceId"]}, handle)
    print(f"Signed in; workspace {chosen['name']!r}; session saved to {SESSION} (valid 12 hours)")


if __name__ == "__main__":
    main()
