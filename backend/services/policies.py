"""Shared product validation and durable settings operations."""

from ..repositories.policies import PoliciesRepository as repository
import json
from ..core.errors import ServiceError
from ..core.models import Strict as Strict, FiniteStrict as FiniteStrict


def backup_policy(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"interval", "retain"}
        or any(type(item) is not int or not 1 <= item <= 1000 for item in value.values())
    ):
        raise ValueError("Backup interval and retention must be integers from 1 to 1000")
    return dict(value)


def read_setting(db, key, default=None):
    row = repository.read_setting_settings(db, (key,)).fetchone()
    return json.loads(row[0]) if row else default


def dispatch_held(db):
    return read_setting(db, "dispatchHold", False)


def set_disabled_workers(db, workers):
    repository.set_disabled_workers_settings(db, ("disabledWorkers", json.dumps(sorted(workers))))


def active_profile(store, current, message="Active account required"):
    profile = store.profile(current["userId"])
    if not profile or profile["accountStatus"] != "ACTIVE":
        raise ServiceError(403, message)
    return profile


def platform_profile(profile, message="Platform administrator required"):
    if not profile.get("platformAdmin"):
        raise ServiceError(403, message)
    return profile


def v2_qualification(profile, model_hash):
    if profile.get("platform") == "windows" or 2 not in profile.get("recipeVersions", []):
        return "recipe"
    if model_hash not in profile.get("qualifiedModelHashes", []):
        return "model"
    return None


def v3_qualification(profile, model_hash, engine=None, decoder=None):
    # A native Windows profile reaches [3] only through the reference-bound worker-only validation of SelfTest.
    if profile.get("recipeVersions") != [3]:
        return "recipe"
    from heteroes.noise.contracts import ENGINE_VERSION
    from heteroes.product.model_qualification import qualification_key

    engine = engine or ENGINE_VERSION
    key = qualification_key(engine, decoder if decoder in (None, "strict_b22_v1") else None)
    by_engine = profile.get("qualifiedModelsByNoiseEngine")
    hashes = (
        by_engine.get(key, [])
        if by_engine is not None
        else (
            profile.get("qualifiedModelHashes", [])
            if key == engine and profile.get("noiseVersion", ENGINE_VERSION) == engine
            else []
        )
    )
    if model_hash not in hashes:
        return "model"
    return None


SHARED_GPU_FRACTION = 0.9  # two weight sets may share a GPU only within this share of its memory


def shared_gpu_bytes(memory, body):
    """
    Estimated peak GPU bytes of one weight set of this run on the measured device, or None when unknown. `memory` is the
    chunk measurement the device took while qualifying the model (heteroes.product.chunk_memory): the model as an FP32
    evaluation holds it (FP16 weights plus an FP32 copy, more than the strict decoder keeps), so the estimate errs high.
    The chunk is the largest the run lets a device use; the memory above the weights scales up with longer generations.
    """
    if not memory:
        return None
    chunk = max(body.get("evalChunks") or [body.get("evalChunk") or 32])
    ran = sorted((c for c in memory["chunks"] if c["ran"] and c["chunk"] >= chunk), key=lambda c: c["chunk"])
    if not ran:
        return None
    measured = memory["promptTokens"] + memory["newTokens"]
    scale = max(1.0, (memory["promptTokens"] + body.get("maxNewTokens", memory["newTokens"])) / measured)
    return memory["baseBytes"] + (ran[0]["peakBytes"] - memory["baseBytes"]) * scale


def strict_layout(body, coordinator, workers, coordinator_memory=None):
    """
    Why a strict run cannot use these devices, or None (D1, ADR-013: one weight set per GPU). The coordinator validates
    and exports with the strict decoder, so it needs a GPU. Its GPU may also work for the run (owner decision
    2026-11-24, relaxing D1) only when two weight sets fit: the coordinator's own measurement of this model
    (`coordinator_memory`, from its qualification) times two stays within SHARED_GPU_FRACTION of that GPU's memory.
    Without a measurement the GPU is not shared. Earlier recipes keep their layouts.
    """
    if body.get("decodeEngine") != "strict_b22_v1" or coordinator is None:
        return None
    from heteroes.product.cpu_coordinator import coordinator_only

    if coordinator_only(coordinator["selfTest"]):
        return "A strict run needs a GPU coordinator: its validation and export use the strict decoder"
    gpu = coordinator.get("physicalResourceId")
    if any(
        w["deviceId"] == coordinator["deviceId"] or (gpu is not None and w.get("physicalResourceId") == gpu)
        for w in workers
        if w
    ):
        need = shared_gpu_bytes(coordinator_memory, body)
        if need is None or 2 * need > SHARED_GPU_FRACTION * coordinator_memory["totalBytes"]:
            return (
                "A strict run keeps one weight set per GPU unless two fit: qualify the model on the coordinator to "
                "measure its memory, or choose a worker on another GPU"
            )
    return None


def noise_qualification(profile, engine):
    """Legacy reports prove v1 only; connectivity never proves engine support."""
    from heteroes.noise.contracts import ENGINE_VERSION, CPU_NOISE_FINGERPRINTS

    engines = profile.get("supportedNoiseEngines")
    if engines is None:
        return None if engine == ENGINE_VERSION else "noise"
    expected = CPU_NOISE_FINGERPRINTS.get(engine)
    return None if expected is not None and engines.get(engine) == expected else "noise"


def display_identity(device, *, source="recorded"):
    """Display metadata only: never part of a recipe, seed or config hash."""
    import time

    profile = device.get("selfTest") or {}
    return {
        "name": device.get("displayName") or device["workerId"],
        "gpuName": profile.get("gpuName"),
        "gpuIndex": profile.get("gpuIndex"),
        "gpuUUID": device.get("physicalResourceId"),
        "deviceId": device.get("deviceId"),
        "ownerUserId": device.get("ownerUserId"),
        "capturedAt": time.time(),
        "source": source,
    }


def storage_status(runtime):
    backend = runtime.storage_backend
    return {
        "cloudStorageConfigured": False,
        "recoveryStorageConfigured": backend is not None,
        "recoveryStorageMode": getattr(backend, "mode", "local") if backend else None,
    }


def has_device_reservation(db, device_id, gpu_uuid=None):
    reserved = repository.has_device_reservation_device_reservations(db, (device_id,)).fetchone()
    physical = repository.has_device_reservation_physical_reservations(db, (gpu_uuid,)).fetchone()
    probe = repository.has_device_reservation_model_probe_reservations(db, (device_id, gpu_uuid)).fetchone()
    return bool(reserved or physical or probe)


def processes_drained(processes):
    return all(p.get("coordinatorAlive") is False and p.get("workerAlive") is False for p in processes)
