#!/usr/bin/env python3
"""Read-only verification of the PUBLIC lab: installers, web pages and (optionally) the live-view API through the tunnel.

    verify-public-lab.py --base https://lab.heteroes.site --out evidence.json [--credentials ~/.config/heteroes-m2/credentials.json]

Downloads every installer in the manifest and checks size and SHA-256. With credentials it signs in as the administrator,
reads one finished run's timeline, opens its event stream (the server ends it) and lists notifications and templates,
then signs out. Nothing is created or changed; the password is never printed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "HeteroES-verify/1"}


def get(url, headers=None, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers={**HEADERS, **(headers or {})}), timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--skip-downloads", action="store_true")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    result = {"base": base, "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    health = json.load(get(base + "/api/v1/health"))
    result["health"] = {key: health.get(key) for key in ("ok", "agentMode", "deviceConfiguration")}
    index = get(base + "/").read().decode()
    result["web"] = {"indexHasAssets": "assets/index-" in index}
    for page in ("/explain", "/login", "/register"):
        result["web"][page] = get(base + page).status
    demo = json.load(get(base + "/demo/run.json"))
    result["web"]["demoRun"] = {
        "jobs": len(demo["jobs"]),
        "gpus": len(demo["workers"]),
        "name": demo["experiment"]["name"],
    }

    manifest = json.load(get(base + "/downloads/manifest.json"))
    result["build"] = manifest["build"]
    result["installers"] = []
    if not args.skip_downloads:
        for group in ("installers", "serverInstallers"):
            for item in manifest[group]:
                digest, size = hashlib.sha256(), 0
                with get(base + urllib.parse.quote(item["url"]), timeout=180) as reply:
                    while chunk := reply.read(1 << 20):
                        digest.update(chunk)
                        size += len(chunk)
                ok = digest.hexdigest() == item["sha256"] and size == item["sizeBytes"]
                result["installers"].append(
                    {"group": group, "platform": item["platform"], "name": item["name"], "ok": ok}
                )
                print("OK " if ok else "BAD", group, item["platform"], size, flush=True)

    if args.credentials:
        users = json.loads(args.credentials.read_text())["users"]
        login = urllib.request.Request(
            base + "/api/v1/auth/login",
            data=json.dumps({"username": "admin", "password": users["admin"]}).encode(),
            headers={**HEADERS, "Content-Type": "application/json"},
        )
        session = json.load(urllib.request.urlopen(login, timeout=30))
        auth = {
            "Authorization": "Bearer " + session["accessToken"],
            "X-Workspace-Id": session["workspaces"][0]["workspaceId"],
        }
        try:
            runs = json.load(get(base + "/api/v1/experiments", auth))
            finished = next(
                run for run in runs if run["status"] == "COMPLETED" and run.get("completedGenerations", 0) > 1
            )
            timeline = json.load(get(base + f"/api/v1/experiments/{finished['experimentId']}/timeline", auth))
            result["timeline"] = {
                "jobs": len(timeline["jobs"]),
                "generations": len(timeline["generations"]),
                "gpus": len(timeline["workers"]),
            }
            started = time.monotonic()
            with get(
                base + f"/api/v1/experiments/{finished['experimentId']}/stream",
                {**auth, "Accept": "text/event-stream"},
                timeout=30,
            ) as stream:
                kinds, content_type = [], stream.headers.get("content-type", "")
                for line in stream:
                    if line.startswith(b"event:"):
                        kinds.append(line[6:].strip().decode())
            result["stream"] = {
                "contentType": content_type,
                "events": kinds,
                "seconds": round(time.monotonic() - started, 2),
            }
            notifications = json.load(get(base + "/api/v1/notifications?limit=5", auth))
            templates = json.load(get(base + "/api/v1/experiment-templates", auth))
            result["notifications"] = {"unread": notifications["unread"], "listed": len(notifications["items"])}
            result["templates"] = len(templates)
        finally:
            urllib.request.urlopen(
                urllib.request.Request(
                    base + "/api/v1/auth/logout",
                    data=b"{}",
                    method="POST",
                    headers={**HEADERS, **auth, "Content-Type": "application/json"},
                ),
                timeout=30,
            ).close()

    result["allOk"] = (
        result["health"]["ok"]
        and result["web"]["indexHasAssets"]
        and all(i["ok"] for i in result["installers"])
        and (
            not args.credentials
            or (
                result["stream"]["events"] == ["timeline", "end"]
                and result["stream"]["contentType"].startswith("text/event-stream")
            )
        )
    )
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({key: result[key] for key in result if key != "installers"}, indent=1))
    raise SystemExit(0 if result["allOk"] else 1)


if __name__ == "__main__":
    main()
