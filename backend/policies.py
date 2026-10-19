"""Shared product validation and durable settings operations."""

import json
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FiniteStrict(Strict):
    model_config = ConfigDict(allow_inf_nan=False)


def backup_policy(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"interval", "retain"}
        or any(type(item) is not int or not 1 <= item <= 1000 for item in value.values())
    ):
        raise ValueError("Backup interval and retention must be integers from 1 to 1000")
    return dict(value)


def read_setting(db, key, default=None):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def dispatch_held(db):
    return read_setting(db, "dispatchHold", False)


def set_disabled_workers(db, workers):
    db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("disabledWorkers", json.dumps(sorted(workers))))


def active_profile(store, current, message="Active account required"):
    profile = store.profile(current["userId"])
    if not profile or profile["accountStatus"] != "ACTIVE":
        raise HTTPException(403, message)
    return profile


def platform_profile(profile, message="Platform administrator required"):
    if not profile.get("platformAdmin"):
        raise HTTPException(403, message)
    return profile


def v2_qualification(profile, model_hash):
    if profile.get("platform") == "windows" or 2 not in profile.get("recipeVersions", []):
        return "recipe"
    if model_hash not in profile.get("qualifiedModelHashes", []):
        return "model"
    return None


def v3_qualification(profile, model_hash):
    # A native Windows profile reaches [3] only through the reference-bound worker-only validation of SelfTest.
    if profile.get("recipeVersions") != [3]:
        return "recipe"
    if model_hash not in profile.get("qualifiedModelHashes", []):
        return "model"
    return None


def storage_status(runtime):
    backend = runtime.storage_backend
    return {
        "cloudStorageConfigured": False,
        "recoveryStorageConfigured": backend is not None,
        "recoveryStorageMode": getattr(backend, "mode", "local") if backend else None,
    }


def has_device_reservation(db, device_id, gpu_uuid=None):
    reserved = db.execute("SELECT 1 FROM device_reservations WHERE device_id=?", (device_id,)).fetchone()
    physical = db.execute("SELECT 1 FROM physical_reservations WHERE resource_id=?", (gpu_uuid,)).fetchone()
    return bool(reserved or physical)


def processes_drained(processes):
    return all(p.get("coordinatorAlive") is False and p.get("workerAlive") is False for p in processes)
