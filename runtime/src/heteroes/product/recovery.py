"""Small per-generation recovery points. Never copies live WAL or process identity."""

import hashlib
import ctypes
import errno
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import uuid
from .files import write_json
from .storage import data_root
from heteroes.recovery_manifest import safe_name, validate_manifest

HEX = re.compile(r"[0-9a-f]{64}")


def publish_new_directory(staging, destination):
    """Refuse replacement; use a final manifest marker on filesystems without renameat2."""
    staging = Path(staging)
    destination = Path(destination)
    if sys.platform.startswith("linux"):
        rename = ctypes.CDLL(None, use_errno=True).renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
            error = ctypes.get_errno()
            if error not in (errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP):
                raise OSError(error, os.strerror(error), str(destination))
            marker = next(
                (
                    name
                    for name in ("manifest.json", "heteroes-export.json", "dispatch-held.flag")
                    if (staging / name).is_file()
                ),
                None,
            )
            if marker is None:
                raise OSError(error, "Filesystem requires a final publication marker", str(destination))
            # NTFS supports exclusive mkdir and file links, but not Linux's
            # RENAME_NOREPLACE flag. Readers accept only directories with the
            # final marker. Failure before it leaves no published checkpoint.
            destination.mkdir(mode=0o700, exist_ok=False)
            try:
                paths = sorted(
                    staging.rglob("*"),
                    key=lambda p: (p.relative_to(staging).as_posix() == marker, len(p.parts), str(p)),
                )
                for source in paths:
                    if source.is_symlink():
                        raise ValueError("Publication source contains a symlink")
                    target = destination / source.relative_to(staging)
                    if source.is_dir():
                        target.mkdir(mode=0o700)
                    else:
                        try:
                            os.link(source, target)
                        except OSError as link_error:
                            if link_error.errno not in (errno.EXDEV, errno.EOPNOTSUPP, errno.EPERM):
                                raise
                            with source.open("rb") as incoming, target.open("xb") as out:
                                shutil.copyfileobj(incoming, out)
                                out.flush()
                                os.fsync(out.fileno())
                shutil.rmtree(staging)
            except BaseException:
                shutil.rmtree(destination, ignore_errors=True)
                raise
    else:
        staging.rename(destination)


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_identity(root):
    """Identify exact runtime bytes even on an isolated GPU without Git metadata."""
    root = Path(root)
    files = {str(path.relative_to(root)): sha256(path) for path in sorted(root.rglob("*.py"))}
    if not files:
        raise ValueError("Runtime sources unavailable")
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"sourceTreeSha256": hashlib.sha256(encoded).hexdigest(), "sourceFiles": files}


def capture_point(root, summary, recipe, policy, final=False, identity=None):
    """Called only after publication and before the next generation opens.

    Published weights are immutable: hard links keep them alive through pruning.
    Their filename already carries the runtime-verified publication SHA. Upload
    and restore still verify full bytes outside the generation barrier.
    """
    root = Path(root)
    generation = summary["generation"]
    if not final and (generation + 1) % policy["interval"]:
        return None
    large = data_root(root)
    destination = large / "recovery-points" / uuid.uuid4().hex
    temporary = destination.with_name(destination.name + ".pending")
    temporary.mkdir(parents=True, mode=0o700)
    files = {}
    try:
        with sqlite3.connect(f"file:{root / 'ledger.sqlite'}?mode=ro", uri=True) as source:
            row = source.execute(
                "SELECT child_weights_sha256,applied_at FROM generation_update WHERE generation=?", (generation,)
            ).fetchone()
            if not row or not row[1] or row[0] != summary["child_sha256"]:
                raise ValueError("Recovery point requires a completed published generation")
            with sqlite3.connect(temporary / "ledger.sqlite") as backup:
                source.backup(backup)
        shutil.copyfile(root / "config.json", temporary / "config.json")
        write_json(temporary / "identity.json", {"recipe": recipe, "deployment": identity or {}})
        for name in ("ledger.sqlite", "config.json", "identity.json"):
            path = temporary / name
            os.chmod(path, 0o600)
            files[name] = {"sha256": sha256(path), "sizeBytes": path.stat().st_size}
        (temporary / "weights").mkdir(mode=0o700)
        for value in {summary["parent_sha256"], summary["child_sha256"]}:
            if not HEX.fullmatch(value):
                raise ValueError("Invalid published hash")
            source = large / "weights" / f"{value}.bin"
            if source.is_symlink() or not source.is_file():
                raise ValueError("Published weights are missing or unsafe")
            os.link(source, temporary / "weights" / source.name)
            files["weights/" + source.name] = {"sha256": value, "sizeBytes": source.stat().st_size}
        version = 1
        if recipe.get("formatVersion") == 3:
            from heteroes.v3.recovery import capture_state, validate_state

            version = 2
            for name in capture_state(root, temporary, recipe, generation):
                path = temporary / name
                files[name] = {"sha256": sha256(path), "sizeBytes": path.stat().st_size}
            validate_state(
                json.loads((temporary / "v3-state.json").read_text()),
                json.loads((temporary / "config.json").read_text()),
                recipe,
                generation,
                files,
            )
        manifest = {
            "formatVersion": version,
            "pointId": destination.name,
            "runId": json.loads((root / "config.json").read_text())["runId"],
            "generation": generation,
            "childWeightsSha256": summary["child_sha256"],
            "parentWeightsSha256": summary["parent_sha256"],
            "final": final,
            "backupPolicy": policy,
            "files": files,
        }
        write_json(temporary / "manifest.json", manifest)
        publish_new_directory(temporary, destination)
        return destination
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


VERIFY_CACHE = "verify-cache.json"


def _file_identity(path):
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns, stat.st_ino, stat.st_dev]


def verify_point(point, cache=False):
    """Check a recovery point's files, ledger and v3 state against its manifest.

    `cache=True` (the upload loop, which retries the same point) skips re-hashing when the manifest bytes and every
    file's size, mtime, inode and device equal those recorded after the last full check. Everything else is still
    checked. A rewrite that restores the old mtime on the same inode is not detected; restore and pause never use it.
    """
    point = Path(point)
    raw = (point / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    validate_manifest(manifest)
    if not {"ledger.sqlite", "config.json", "identity.json"} <= manifest["files"].keys():
        raise ValueError("Incomplete manifest")
    key = hashlib.sha256(raw).hexdigest()
    identities = {}
    for name in manifest["files"]:
        if not safe_name(name, manifest["formatVersion"]):
            raise ValueError("Unsafe recovery path")
        path = point / name
        if any(p.is_symlink() for p in [point, path.parent, path]) or not path.is_file():
            raise ValueError("Missing or unsafe recovery file")
        identities[name] = _file_identity(path)
    try:
        cached = cache and json.loads((point / VERIFY_CACHE).read_text()) == {
            "formatVersion": 1,
            "manifestSha256": key,
            "files": identities,
        }
    except (OSError, ValueError):
        cached = False
    for name, meta in manifest["files"].items():
        if type(meta.get("sizeBytes")) is not int or identities[name][0] != meta["sizeBytes"]:
            raise ValueError("Recovery checksum mismatch")
        if not cached and sha256(point / name) != meta["sha256"]:
            raise ValueError("Recovery checksum mismatch")
    if f"weights/{manifest['childWeightsSha256']}.bin" not in manifest["files"]:
        raise ValueError("Missing canonical child")
    if f"weights/{manifest['parentWeightsSha256']}.bin" not in manifest["files"]:
        raise ValueError("Missing canonical parent")
    with sqlite3.connect(f"file:{point / 'ledger.sqlite'}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Invalid ledger snapshot")
        row = db.execute(
            "SELECT child_weights_sha256,applied_at FROM generation_update WHERE generation=?",
            (manifest["generation"],),
        ).fetchone()
        if not row or row[0] != manifest["childWeightsSha256"] or not row[1]:
            raise ValueError("Ledger and weights disagree")
        if (
            db.execute("SELECT max(generation) FROM generation_update WHERE applied_at IS NOT NULL").fetchone()[0]
            != manifest["generation"]
        ):
            raise ValueError("Ledger is ahead of recovery weights")
    if json.loads((point / "config.json").read_text())["runId"] != manifest["runId"]:
        raise ValueError("Run identity mismatch")
    config = json.loads((point / "config.json").read_text())
    if config.get("recipeVersion") == 3:
        if manifest["formatVersion"] != 2:
            raise ValueError("Incomplete v3 recovery point")
        from heteroes.v3.recovery import validate_state

        validate_state(
            json.loads((point / "v3-state.json").read_text()),
            config,
            json.loads((point / "identity.json").read_text())["recipe"],
            manifest["generation"],
            manifest["files"],
        )
    elif manifest["formatVersion"] == 2:
        raise ValueError("V3 recovery requires a v3 config")
    if cache and not cached:
        write_json(point / VERIFY_CACHE, {"formatVersion": 1, "manifestSha256": key, "files": identities})
    return manifest


def restore_point(point, destination):
    point = Path(point)
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    manifest = verify_point(point)
    temporary = destination.with_name(destination.name + ".restoring-" + uuid.uuid4().hex)
    temporary.mkdir(parents=True, mode=0o700)
    try:
        for name in manifest["files"]:
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(point / name, target)
            os.chmod(target, 0o600)
        if manifest["formatVersion"] == 2:
            from heteroes.v3.recovery import restore_state

            restore_state(point, temporary, destination)
        write_json(temporary / "recovery-lineage.json", manifest)
        write_json(temporary / "backup-policy.json", manifest["backupPolicy"])
        write_json(
            temporary / "state.json",
            {
                "status": "RECOVERING",
                "recoveryCount": 0,
                "workersLaunched": False,
                "workerStates": {},
                "startedAt": __import__("time").time(),
            },
        )
        (temporary / "dispatch-held.flag").touch(mode=0o600)
        publish_new_directory(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination
