"""Local cleanup of a finished run's large data on its coordinator.

A finished 1.5B run kept about 20 GB on the coordinator (26/11: the system disk fell to 7.6 GB). Once the run is over and
its newest recovery point is verified by the lab's store (the lab compared every object's SHA-256 with the manifest and
answered READY), the local weights, the selection copy and the local recovery points are no longer the only copy of
anything the run can continue from. They are removed; the ledger, events, usage and settings of the run (on the state
disk) and the verified export of the result model stay.

Nothing is removed while: the run is not COMPLETED, CANCELLED or FAILED; it ended less than `GRACE_SECONDS` ago; no local
point is READY, or a newer local point than the READY one exists (its upload is still pending or failed); or a receipt
says the cleanup already ran. A receipt (`local-cleanup.json`) records what was removed and the lab point kept.
"""

import os
import shutil
import time
from pathlib import Path

from .files import read_json, write_json
from .storage import data_root

TERMINAL = {"COMPLETED", "CANCELLED", "FAILED"}
GRACE_SECONDS = 15 * 60  # the notebook or the lab may still read the run's final files for a few minutes
REMOVABLE = ("weights", "selection", "recovery-points")  # under the run's large-data directory
RECEIPT = "local-cleanup.json"
KEEP_ENV = "HETEROES_KEEP_FINISHED_RUN_DATA"  # "1": never clean automatically (the CLI dry run still reports)


def _size(path):
    files = {}
    for f in Path(path).rglob("*"):
        if f.is_file() and not f.is_symlink():
            stat = f.stat()
            files[(stat.st_dev, stat.st_ino)] = stat.st_size  # a hard link counts once
    return sum(files.values())


def _points(large):
    points = []
    for p in (large / "recovery-points").glob("*"):
        manifest = read_json(p / "manifest.json") if p.is_dir() else None
        if manifest:
            points.append((manifest["generation"], bool(manifest.get("final")), p))
    points.sort(key=lambda item: (item[0], item[1]), reverse=True)  # newest first; a final point before a plain one
    return points


def plan(root, now=None):
    """What cleaning run state directory `root` would remove, or why it would not: a dict with `eligible`, `reason`,
    `remove` (paths), `bytes`, and the lab point it relies on."""
    root = Path(root)
    now = time.time() if now is None else now
    out = {"runId": root.name, "eligible": False, "remove": [], "bytes": 0}
    if read_json(root / RECEIPT):
        return out | {"reason": "already cleaned"}
    state = read_json(root / "state.json", {})
    status = state.get("status")
    if status not in TERMINAL:
        return out | {"reason": f"run is {status or 'unknown'}"}
    ended = state.get("updatedAt") or 0
    if now - ended < GRACE_SECONDS:
        return out | {"reason": "ended less than 15 minutes ago"}
    try:
        large = data_root(root)
    except (OSError, ValueError) as error:  # the large-data volume is not mounted: nothing to judge from
        return out | {"reason": f"large-data directory unavailable ({type(error).__name__})"}
    points = _points(large)
    if not points:
        present = [large / name for name in REMOVABLE if (large / name).exists()]
        return out | {"reason": "no recovery point on this machine" if present else "nothing to remove"}
    generation, final, newest = points[0]
    cloud = read_json(newest / "cloud-state.json", {})
    if cloud.get("status") != "READY":
        return out | {
            "reason": f"newest point (generation {generation}) is not verified by the lab store "
            f"({cloud.get('status') or 'not uploaded'})"
        }
    remove = [large / name for name in REMOVABLE if (large / name).exists()]
    if not remove:
        return out | {"reason": "nothing to remove"}
    manifest = read_json(newest / "manifest.json")
    return out | {
        "eligible": True,
        "reason": "finished; newest point verified by the lab store",
        "remove": remove,
        "bytes": sum(_size(p) for p in remove),
        "labPoint": {
            "pointId": manifest.get("pointId", newest.name),
            "generation": generation,
            "final": final,
            "files": {k: v["sha256"] for k, v in (manifest.get("files") or {}).items()},
        },
        "status": status,
    }


def apply(root, now=None):
    """Clean one run when `plan` allows it; returns the plan (with `removed` when it acted). The receipt is written
    before the bytes go, so an interrupted cleanup is finished by the next call instead of being retried as new."""
    root = Path(root)
    pending = read_json(root / RECEIPT)
    if pending and pending.get("state") == "removing":
        for path in pending["remove"]:
            shutil.rmtree(path, ignore_errors=True)
        write_json(root / RECEIPT, pending | {"state": "done", "doneAt": time.time()})
        return pending | {"removed": True}
    decided = plan(root, now)
    if not decided["eligible"]:
        return decided
    receipt = {
        "state": "removing",
        "t": time.time(),
        "runStatus": decided["status"],
        "labPoint": decided["labPoint"],
        "remove": [str(p) for p in decided["remove"]],
        "freedBytes": decided["bytes"],
        "kept": "ledger, events, usage and settings (state disk); export of the result model",
    }
    write_json(root / RECEIPT, receipt)
    for path in decided["remove"]:
        shutil.rmtree(path, ignore_errors=True)
    write_json(root / RECEIPT, receipt | {"state": "done", "doneAt": time.time()})
    return decided | {"removed": True}


def automatic():
    return os.environ.get(KEEP_ENV) != "1"
