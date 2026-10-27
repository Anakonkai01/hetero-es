"""Asynchronous recovery upload, using scoped URLs and no cloud master keys."""

import hashlib
import shutil
import threading
import time
import urllib.request
from .files import read_json, write_json
from .recovery import verify_point
from .storage import data_root

# M3: an object is streamed in blocks of this size, never read whole into memory (weights are about 1 GB each)
UPLOAD_BLOCK = 1 << 20
# M3: after a failed cycle a run waits 30 s, doubling per consecutive failure up to an hour; kept across restarts
BACKOFF_FIRST, BACKOFF_CAP = 30.0, 3600.0


class _Section:
    """A bounded, read-once view of `size` bytes from `offset`, hashed as it is sent."""

    def __init__(self, stream, offset, size, digest):
        stream.seek(offset)
        self.stream, self.size, self.left, self.digest = stream, size, size, digest

    def read(self, size=-1):
        size = UPLOAD_BLOCK if size is None or size < 0 else min(size, UPLOAD_BLOCK)
        data = self.stream.read(min(size, self.left))
        if not data and self.left:
            raise ValueError("Local recovery point changed")
        self.left -= len(data)
        self.digest.update(data)
        return data


class CloudSync:
    def __init__(self, agent, clock=time.time):
        self.agent = agent
        self.clock = clock
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def _put(self, url, stream, offset, size, digest, headers):
        body = _Section(stream, offset, size, digest)
        request = urllib.request.Request(url, data=body, method="PUT", headers={**headers, "Content-Length": str(size)})
        with urllib.request.urlopen(request, timeout=180) as response:
            etag = response.headers["ETag"]
            response.read()
        if body.left:
            raise ValueError("Local recovery point changed")
        return etag

    def upload(self, point, assignment):
        manifest = verify_point(point, cache=True)
        body = {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "manifest": manifest}
        plan = self.agent.call("/api/v1/device/recovery-points", body)
        write_json(point / "cloud-state.json", {"status": plan["status"], "remoteCreated": True, "t": time.time()})
        for obj in plan["objects"]:
            source = next(point / name for name, meta in manifest["files"].items() if meta["sha256"] == obj["sha256"])
            parts, digest = [], hashlib.sha256()
            with open(source, "rb") as stream:
                if obj["mode"] == "single":
                    self._put(obj["url"], stream, 0, obj["sizeBytes"], digest, obj["headers"])
                else:
                    for part in obj["parts"]:  # in order, so the running hash covers the whole object
                        etag = self._put(part["url"], stream, part["offset"], part["sizeBytes"], digest, {})
                        parts.append({"PartNumber": part["number"], "ETag": etag})
            # the bytes sent must be the verified ones: a point rewritten during upload is never completed
            if digest.hexdigest() != obj["sha256"]:
                raise ValueError("Local recovery point changed")
            self.agent.call(
                "/api/v1/device/recovery-points/complete-object",
                {
                    "assignmentId": assignment["assignmentId"],
                    "epoch": assignment["epoch"],
                    "pointId": manifest["pointId"],
                    "sha256": obj["sha256"],
                    "parts": parts,
                },
            )
        self.agent.call(
            "/api/v1/device/recovery-points/" + manifest["pointId"] + "/verify",
            {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"]},
        )
        return manifest

    def _sync(self, root, assignment, points):
        """Remote cleanup and upload of one run; returns False when a network step failed."""
        cleanup = read_json(root / "cloud-cleanup.json", [])
        remaining = []
        for point_id in cleanup:
            try:
                self.agent.call(
                    "/api/v1/device/recovery-points/" + point_id,
                    {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"]},
                    method="DELETE",
                )
            except urllib.error.HTTPError as error:
                if error.code != 404:
                    remaining.append(point_id)
            except Exception:
                remaining.append(point_id)
        write_json(root / "cloud-cleanup.json", remaining)
        for point in points:
            status = read_json(point / "cloud-state.json", {})
            if status.get("status") == "READY":
                continue
            try:
                if status.get("status") == "VERIFYING":
                    result = self.agent.call("/api/v1/device/recovery-points/" + point.name, None)
                    if result["status"] == "READY":
                        write_json(
                            point / "cloud-state.json", {"status": "READY", "remoteCreated": True, "t": time.time()}
                        )
                        write_json(
                            root / "cloud-sync.json",
                            {
                                "status": "READY",
                                "lastCloudGeneration": read_json(point / "manifest.json")["generation"],
                                "pointId": point.name,
                                "t": time.time(),
                            },
                        )
                        continue
                    if result["status"] != "ERROR":
                        continue
                self.upload(point, assignment)
                write_json(point / "cloud-state.json", {"status": "VERIFYING", "t": time.time()})
            except Exception as error:
                failures = read_json(root / "cloud-backoff.json", {}).get("failures", 0) + 1
                retry = self.clock() + min(BACKOFF_CAP, BACKOFF_FIRST * 2 ** (failures - 1))
                write_json(root / "cloud-backoff.json", {"failures": failures, "retryAt": retry})
                write_json(
                    root / "cloud-sync.json",
                    {"status": "PENDING", "errorType": type(error).__name__, "t": time.time(), "retryAt": retry},
                )
                return False
        return not remaining

    def cycle(self):
        for root in self.agent.manager.root.iterdir():
            if not root.is_dir():
                continue
            assignment = read_json(root / "assignment.json")
            if not assignment:
                continue
            points = [
                p
                for p in (data_root(root) / "recovery-points").glob("*")
                if p.is_dir() and (p / "manifest.json").exists()
            ]
            points.sort(key=lambda p: (read_json(p / "manifest.json")["generation"], p.stat().st_mtime), reverse=True)
            backoff = read_json(root / "cloud-backoff.json", {})
            if self.clock() >= backoff.get("retryAt", 0):
                synced = self._sync(root, assignment, points)
                if synced and backoff:
                    (root / "cloud-backoff.json").unlink(missing_ok=True)
            # Bound local unuploaded points without deleting the current upload.
            # This cycle is single-threaded; a newly created point is included next.
            retain = (
                read_json(points[0] / "manifest.json")["backupPolicy"]["retain"]
                if points
                else assignment["config"].get("backupPolicy", {"retain": 3})["retain"]
            )
            # Dependencies outside the retention count: the newest cloud-verified point stays (local and remote)
            # until a newer one is verified, and a paused run keeps the point it resumes from.
            keep = {
                next((p.name for p in points if read_json(p / "cloud-state.json", {}).get("status") == "READY"), None),
                read_json(root / "pause-point.json", {}).get("pointId"),
            }
            remaining = read_json(root / "cloud-cleanup.json", [])
            ordinary = [p for p in points if not read_json(p / "manifest.json")["final"]]
            for point in ordinary[retain:]:
                if point.name in keep:
                    continue
                if read_json(point / "cloud-state.json", {}).get("remoteCreated"):
                    remaining.append(point.name)
                    # Persist the cleanup intent before removing the local bytes.
                    write_json(root / "cloud-cleanup.json", list(dict.fromkeys(remaining)))
                shutil.rmtree(point)

    def run(self):
        while not self.stop.is_set():
            try:
                self.cycle()
            except Exception as error:
                write_json(self.agent.root / "cloud-error.json", {"errorType": type(error).__name__, "t": time.time()})
            self.stop.wait(30)
