#!/usr/bin/env python3
"""Import a historical recovery point or restore a verified local point, without exposing secrets."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["import", "restore"])
    p.add_argument("--url", required=True)
    p.add_argument("--workspace", default="lab")
    p.add_argument("--username", default="admin")
    p.add_argument("--runtime-root", required=True, type=Path)
    p.add_argument("--point", type=Path)
    p.add_argument("--point-id")
    p.add_argument("--destination", type=Path)
    p.add_argument(
        "--credentials-file", type=Path, help="Optional private credentials.json; otherwise password is prompted"
    )
    a = p.parse_args()
    sys.path.insert(0, str(a.runtime_root / "src"))
    from heteroes.product.recovery import verify_point, restore_point

    token = None

    def call(path, body=None, method=None):
        headers = {"Content-Type": "application/json", "X-Workspace-Id": a.workspace}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(
            a.url.rstrip("/") + "/api/v1" + path,
            data=None if body is None else json.dumps(body).encode(),
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else {}

    password = (
        json.loads(a.credentials_file.read_text())["users"][a.username]
        if a.credentials_file
        else getpass.getpass("Password: ")
    )
    try:
        token = call("/auth/login", {"username": a.username, "password": password})["accessToken"]
        password = None
        if a.action == "import":
            if a.point is None:
                p.error("import requires --point")
            m = verify_point(a.point)
            base = "/experiments/" + m["runId"] + "/recovery-import"
            plan = call(base, m)
            for obj in plan["objects"]:
                source = next(a.point / name for name, meta in m["files"].items() if meta["sha256"] == obj["sha256"])
                parts = []
                with open(source, "rb") as stream:
                    entries = (
                        obj["parts"]
                        if obj["mode"] == "multipart"
                        else [{"number": 1, "offset": 0, "sizeBytes": obj["sizeBytes"], "url": obj["url"]}]
                    )
                    for part in entries:
                        stream.seek(part["offset"])
                        data = stream.read(part["sizeBytes"])
                        if len(data) != part["sizeBytes"]:
                            raise ValueError("Local object changed")
                        req = urllib.request.Request(
                            part["url"], data=data, method="PUT", headers={"Content-Length": str(len(data))}
                        )
                        with urllib.request.urlopen(req, timeout=180) as response:
                            if obj["mode"] == "multipart":
                                parts.append({"PartNumber": part["number"], "ETag": response.headers["ETag"]})
                            response.read()
                call(base + "/complete-object", {"pointId": m["pointId"], "sha256": obj["sha256"], "parts": parts})
            call(base + "/" + m["pointId"] + "/verify", {})
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                status = next(
                    x for x in call("/experiments/" + m["runId"] + "/recovery-points") if x["pointId"] == m["pointId"]
                )
                if status["status"] == "READY":
                    print(json.dumps({"status": "READY", "pointId": m["pointId"], "sha256": m["childWeightsSha256"]}))
                    return 0
                if status["status"] == "ERROR":
                    raise RuntimeError("Cloud verification failed")
                time.sleep(2)
            raise TimeoutError("Verification remains pending")
        if not a.point_id or a.destination is None:
            p.error("restore requires --point-id and --destination")
        if a.destination.exists():
            raise FileExistsError("Use a new destination")
        a.destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=a.destination.parent, prefix="recovery-") as temporary:
            point = Path(temporary)
            os.chmod(point, 0o700)
            plan = call("/recovery-points/" + a.point_id + "/download-plan", {})
            m = plan["manifest"]
            (point / "manifest.json").write_text(json.dumps(m))
            os.chmod(point / "manifest.json", 0o600)
            for name in m["files"]:
                # Refresh short-lived rights before starting each large download.
                current = call("/recovery-points/" + a.point_id + "/download-plan", {})
                if current["manifest"] != m:
                    raise ValueError("Recovery manifest changed")
                from heteroes.product.recovery import safe_name

                if not safe_name(name):
                    raise ValueError("Unsafe recovery path")
                target = point / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with (
                    urllib.request.urlopen(current["objects"][name], timeout=180) as response,
                    open(target, "wb") as stream,
                ):
                    os.chmod(target, 0o600)
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > m["files"][name]["sizeBytes"]:
                            raise ValueError("Cloud object exceeded manifest size")
                        stream.write(chunk)
            verify_point(point)
            restore_point(point, a.destination)
        print(
            json.dumps(
                {"restored": True, "dispatchHeld": True, "pointId": a.point_id, "sha256": m["childWeightsSha256"]}
            )
        )
        return 0
    except Exception as error:
        # HTTP errors can contain presigned URLs; only print the exception type.
        print("Cloud recovery failed: " + type(error).__name__, file=sys.stderr)
        return 1
    finally:
        if token:
            try:
                call("/auth/logout", {}, method="POST")
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
