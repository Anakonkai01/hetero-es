"""SchedulingService business operations behind the Store facade."""

import json
from ..core.clock import now
from ..core.constants import ACTIVE, TERMINAL, V3_CODE_KEYS, V3_KEYS, V3_UPDATE_KEYS
from backend.core.errors import RuntimeRejected
from .policies import dispatch_held
from ..repositories.scheduling import SchedulingRepository as repository
from ..db.transactions import begin_write


class SchedulingService:
    def __init__(self, store):
        self.store = store

    def dispatch_once(self):
        with self.store.operation_lock:
            self.store._dispatch_once()

    def _dispatch_once(self):
        """Always reconcile admitted work; hold only admission of new queued work."""
        errors = []
        for active in [body for body in self.store.list() if body["status"] in ACTIVE]:
            try:
                self.store._dispatch_run(active)
                with self.store.db() as db:
                    begin_write(db)
                    self.store.runtime.auto_join(
                        db, self.store.get(active["experimentId"])
                    )  # it checks allowJoin itself
            except Exception as error:
                errors.append(type(error).__name__)
        with self.store.db() as db:
            queued = [row[0] for row in repository._dispatch_once_select_queue(db, ())]
        for run_id in queued:
            with self.store.db() as db:
                # Recheck under the same lock as the queued-to-STARTING claim.
                # An operator can hold admission while reconciliation is running.
                if dispatch_held(db):
                    break
                active = self.store.get(run_id)
                if not active or active["status"] != "QUEUED":
                    continue
                if reason := self.store.eligibility(db, active):
                    active.update(status="CANCELLED", cancelRequested=True, completedAt=now(), failureReason=reason)
                    self.store.save(db, active)
                    repository._dispatch_once_delete_queue(db, (run_id,))
                    self.store.audit(db, "system", "QUEUE_ACCESS_REVOKED", run_id, active["workspaceId"])
                    continue
                if waiting := self.store.runtime.waiting_reason(active):
                    active["waitingReason"] = waiting
                    self.store.save(db, active)
                    continue
                active.pop("waitingReason", None)
                active.update(status="STARTING", startedAt=now())
                self.store.save(db, active)
            # Reserve before considering the next job; retry this frozen run on
            # lost responses, and keep unrelated jobs progressing through errors.
            try:
                self.store._dispatch_run(active)
            except Exception as error:
                errors.append(type(error).__name__)
        self.store.last_error = errors[0] if errors else None

    def _dispatch_run(self, active):
        run_id = active["experimentId"]
        # Submission can succeed while its response is lost. The runtime rejects
        # changes to an existing run and accepts retries of this exact payload.
        config = {
            "runId": run_id,
            "workerIds": active["workerIds"],
            "workload": active["task"],
            **{
                key: active[key]
                for key in (
                    "candidatesPerGeneration",
                    "maxGenerations",
                    "alpha",
                    "sigma",
                    "decodeEngine",
                    "schedulerPolicy",
                    "syncMode",
                )
            },
        }
        config.update(
            coordinatorDeviceId=active["coordinatorDeviceId"],
            backupPolicy=active.get("backupPolicy", {"interval": 1, "retain": 3}),
        )
        if active.get("recipeVersion") in (2, 3):
            config.update(
                {
                    key: active[key]
                    for key in (
                        "recipeVersion",
                        "modelManifest",
                        "modelSource",
                        "datasetObjectSha256",
                        "datasetIdentity",
                        "batchSize",
                        "batchSeed",
                        "sigmaSchedule",
                        "sigmaMinimum",
                        "maxNewTokens",
                        "validationInterval",
                    )
                }
            )
        if "datasetSplitObjects" in active:  # a file-backed dataset (format 3)
            config["datasetSplitObjects"] = active["datasetSplitObjects"]
        if active.get("recipeVersion") == 3:
            config.update({key: active[key] for key in V3_KEYS})
            config.update({key: active[key] for key in (*V3_UPDATE_KEYS, *V3_CODE_KEYS) if key in active})
        try:
            self.store.runtime.submit(config)
        except RuntimeRejected as error:
            with self.store.db() as db:
                body = self.store.get(run_id)
                body.update(status="FAILED", failureReason=str(error), completedAt=now())
                self.store.save(db, body)
                repository._dispatch_run_delete_queue_3(db, (run_id,))
            return
        current = self.store.get(run_id)
        if current.get("cancelRequested"):
            self.store.runtime.cancel(run_id)
        elif current.get("pauseRequested"):
            self.store.runtime.pause(run_id)
        snapshot = self.store.runtime.snapshot(run_id)
        with self.store.db() as db:
            body = self.store.get(run_id)
            state = snapshot["state"]
            body["status"] = state["status"]
            if body.get("cancelRequested") and body["status"] == "PAUSED":
                body["status"] = "CANCELLED"
            if (
                body.get("pauseRequested")
                and not body.get("cancelRequested")
                and body["status"] in ("STARTING", "RUNNING")
            ):
                body["status"] = "PAUSING"
            if state.get("pauseCheckpoint"):
                body["pauseCheckpoint"] = state["pauseCheckpoint"]
            if body["status"] == "PAUSED":
                body["pausedAt"] = now()
                repository._dispatch_run_delete_queue(db, (run_id,))
            if "cloudSync" in snapshot:
                previous = body.get("cloudSync", {})
                incoming = snapshot["cloudSync"]
                body["cloudSync"] = {**incoming}
                if previous.get("lastCloudGeneration", -1) > incoming.get("lastCloudGeneration", -1):
                    body["cloudSync"].update(
                        {k: previous[k] for k in ("lastCloudGeneration", "pointId") if k in previous}
                    )
            generations = snapshot["generations"]
            complete = [item for item in generations if item["status"] == "COMPLETED"]
            body["completedGenerations"] = snapshot.get("completedGenerationCount", len(complete))
            body["monitoringPartial"] = bool(snapshot.get("monitoringPartial"))
            body["workerBlocks"] = {
                worker: {"reason": value["stopReason"], "blockedAt": value.get("blockedAt")}
                for worker, value in state.get("workerStates", {}).items()
                if value.get("stopReason")
            }
            if snapshot.get("auditSummary") is not None:
                body["auditSummary"] = snapshot["auditSummary"]
            if isinstance(
                snapshot.get("membership"), dict
            ):  # who works on it now, as its coordinator recorded (ADR-009)
                body["membership"] = {
                    key: snapshot["membership"].get(key, []) for key in ("members", "left", "refused")
                } | {"generation": snapshot["membership"].get("generation")}
            if snapshot.get("usageSummary") is not None:
                body["usageSummary"] = snapshot["usageSummary"]
            if snapshot.get("studyMetrics"):
                body["studyMetrics"] = snapshot["studyMetrics"]
                best = snapshot["studyMetrics"].get("best") or {}
                if "validationAccuracy" in best:
                    body["validationScore"] = best["validationAccuracy"]
                if "validationReward" in best:
                    body["validationScore"] = best["validationReward"]
                if "testReward" in snapshot["studyMetrics"]:
                    body["testScore"] = snapshot["studyMetrics"]["testReward"]
                if "testAccuracy" in snapshot["studyMetrics"]:
                    body["testScore"] = snapshot["studyMetrics"]["testAccuracy"]
            latest = snapshot.get("latestGeneration") or (generations[-1] if generations else None)
            if latest:
                body["currentGenerationId"] = latest["generationId"]
                body["committedCandidateCount"] = latest["committedCandidateCount"]
                body["modelVersion"] = latest["modelVersion"]
            if "failureReason" in state:
                body["failureReason"] = state["failureReason"]
            if state.get("finalWeightsSha256"):
                body["modelVersion"] = state["finalWeightsSha256"]
            elif body["status"] in TERMINAL and snapshot.get("checkpointSha256"):
                body["modelVersion"] = snapshot["checkpointSha256"]
            if body["status"] in TERMINAL:
                body["completedAt"] = now()
                repository._dispatch_run_delete_queue_2(db, (run_id,))
            self.store.save(db, body)
            repository._dispatch_run_update_experiments(db, (json.dumps(snapshot, allow_nan=False), run_id))

    def dispatch(self, stop):
        while not stop.wait(1):
            try:
                self.store.dispatch_once()
            except Exception as error:
                self.store.last_error = type(error).__name__
