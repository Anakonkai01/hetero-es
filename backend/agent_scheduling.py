"""CPU-only device control. Connectivity is never evidence of process death."""

from .constants import CORE_COMMAND_KINDS, COMMAND_KINDS

from .policies import v2_qualification, v3_qualification
import json
import secrets
import time
import uuid

from fastapi import HTTPException
from .errors import RuntimeRejected
from heteroes.study.data import sha as study_hash

from .constants import QUIESCENT
from heteroes.product.cpu_coordinator import coordinator_only


class AgentScheduling:
    def waiting_reason(self, body, db=None):
        if db is None:
            with self.store.db() as connection:
                return self.waiting_reason(body, connection)
        devices = self.devices(db)
        by_id = {d["deviceId"]: d for d in devices}
        by_worker = {d["workerId"]: d for d in devices}
        coordinator = by_id.get(body.get("coordinatorDeviceId"))
        if not coordinator or not coordinator["selfTest"].get("coordinator"):
            return "Select an approved coordinator device"
        chosen = [coordinator] + [by_worker.get(w) for w in body["workerIds"]]
        if any(d and coordinator_only(d["selfTest"]) for d in chosen[1:]):
            return "CPU coordinator-only devices cannot be selected as workers"
        for d in chosen:
            if not d or d["approvalStatus"] != "APPROVED":
                return "Selected device needs approval"
            capabilities = db.execute(
                "SELECT value FROM settings WHERE key=?", ("agentCommands:" + d["deviceId"],)
            ).fetchone()
            supported = set(json.loads(capabilities[0])) if capabilities else CORE_COMMAND_KINDS
            if not CORE_COMMAND_KINDS <= supported:
                return "Update selected device agent to support core lifecycle commands"
            cpu_coordinator = coordinator_only(d["selfTest"])
            if cpu_coordinator and body.get("recipeVersion") != 3:
                return "Recipe v3 qualification required"
            if body.get("recipeVersion") in (2, 3) and not cpu_coordinator:
                profile = d["selfTest"]
                version = body["recipeVersion"]
                qualification = (v3_qualification if version == 3 else v2_qualification)(
                    profile, study_hash(body["modelManifest"])
                )
                if qualification == "recipe":
                    return f"Recipe v{version} qualification required"
                if qualification == "model":
                    return "Pinned model qualification required"
            if not d["physicalResourceId"] and not cpu_coordinator:
                return "Refresh selected device self-test to identify its physical GPU"
            if d["connectionStatus"] != "ONLINE":
                return "Waiting for selected device to reconnect"
            if not d["contributionEnabled"]:
                return "Waiting for owner to turn contribution ON"
            if d["allocatedTo"] and d["allocatedTo"] != body["experimentId"]:
                return "Waiting for confirmed GPU release"
            reservation = db.execute(
                "SELECT a.run_id FROM physical_reservations r JOIN assignments a ON a.id=r.assignment_id WHERE resource_id=?",
                (d["physicalResourceId"],),
            ).fetchone()
            if reservation and reservation[0] != body["experimentId"]:
                return "Waiting for confirmed physical GPU release"
        # An old assignment lacking a UUID may be the same GPU as a new alias.
        for reserved in db.execute("SELECT d.self_test FROM device_reservations r JOIN devices d ON d.id=r.device_id"):
            profile = json.loads(reserved[0])
            if not profile.get("gpuUUID") and not coordinator_only(profile):
                return "Waiting for legacy ownership release before physical GPU scheduling"
        workers = [by_worker[w]["physicalResourceId"] for w in body["workerIds"]]
        if len(set(workers)) != len(workers):
            return "Selected worker aliases refer to the same physical GPU"
        return None

    def reservations(self):
        with self.store.db() as db:
            return [
                {"deviceId": r["device_id"], "assignmentId": r["assignment_id"]}
                for r in db.execute("SELECT * FROM device_reservations")
            ]

    def _assignment(self, db, assignment_id):
        row = db.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Assignment not found")
        return row, json.loads(row["body"])

    def submit(self, config):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (config["runId"],)
            ).fetchone()
            body = self.store.get(config["runId"])
            if old:
                if json.loads(old["body"])["config"] != config:
                    raise RuntimeRejected("Frozen assignment cannot change")
                if not body.get("resumeRequested"):
                    return
                if not old["released"] or json.loads(old["snapshot"])["state"]["status"] != "PAUSED":
                    raise RuntimeRejected("Resume requires a released paused assignment")
            if reason := self.waiting_reason(body, db):
                raise ConnectionError(reason)
            devices = self.devices(db)
            by_id = {d["deviceId"]: d for d in devices}
            by_worker = {d["workerId"]: d for d in devices}
            co = by_id[config["coordinatorDeviceId"]]
            chosen = {d["deviceId"]: d for d in [co] + [by_worker[w] for w in config["workerIds"]]}
            aid = uuid.uuid4().hex
            # Secrets are random per device/run, stored only in the private product DB.
            grants = {
                d["workerId"]: secrets.token_urlsafe(32)
                for d in chosen.values()
                if d["workerId"] in config["workerIds"]
            }
            assignment = {
                "assignmentId": aid,
                "runId": config["runId"],
                "coordinatorDeviceId": co["deviceId"],
                "epoch": old["epoch"] + 1 if old else 1,
                "deviceIds": list(chosen),
                "config": config,
                "computeUrl": co["computeUrl"],
                "bulkUrl": co["bulkUrl"],
                "workerDevices": {w: by_worker[w]["deviceId"] for w in config["workerIds"]},
                "computeGrants": grants,
            }
            snap = {
                "state": {"status": "STARTING"},
                "generations": [],
                "candidates": [],
                "attempts": [],
                "events": [],
                "artifacts": [],
            }
            if old:
                prior = json.loads(old["snapshot"])
                assignment["resumeFrom"] = prior["state"]["pauseCheckpoint"]
                snap = {**prior, "state": {"status": "STARTING"}}
            db.execute(
                "INSERT INTO assignments VALUES (?,?,?,?,?,?,0)",
                (aid, config["runId"], co["deviceId"], assignment["epoch"], json.dumps(assignment), json.dumps(snap)),
            )
            for did in chosen:
                db.execute("INSERT INTO device_reservations VALUES (?,?)", (did, aid))
            for resource in {d["physicalResourceId"] for d in chosen.values()}:
                if resource is not None:  # CPU coordinators own their device, never a physical GPU
                    db.execute("INSERT INTO physical_reservations VALUES (?,?)", (resource, aid))
            self.enqueue(
                db,
                co["deviceId"],
                "COORDINATE",
                {**assignment, "effectiveBackupPolicy": body.get("requestedBackupPolicy") or config["backupPolicy"]},
                "coordinate:" + aid,
            )
            body["resumeRequested"] = False
            body["pauseRequested"] = False
            self.store.save(db, body)
            self.store.audit(db, "system", "ASSIGNMENT_CREATED", aid, body["workspaceId"])

    def cancel(self, run_id, db=None):
        if db is None:
            with self.store.db() as connection:
                return self.cancel(run_id, connection)
        row = db.execute(
            "SELECT id,body,released FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (run_id,)
        ).fetchone()
        if not row or row["released"]:
            return
        ar = json.loads(row["body"])
        for did in ar["deviceIds"]:
            self.enqueue(
                db,
                did,
                "CANCEL_ASSIGNMENT",
                {"assignmentId": ar["assignmentId"], "epoch": ar["epoch"]},
                "cancel:" + ar["assignmentId"] + ":" + did,
            )

    def pause(self, run_id, db=None):
        if db is None:
            with self.store.db() as connection:
                return self.pause(run_id, db=connection)
        row = db.execute("SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (run_id,)).fetchone()
        if not row or row["released"]:
            return
        self.require_command(db, row["coordinator"], "PAUSE_ASSIGNMENT")
        self.enqueue(
            db,
            row["coordinator"],
            "PAUSE_ASSIGNMENT",
            {"assignmentId": row["id"], "epoch": row["epoch"]},
            "pause:" + row["id"],
        )

    def _release_confirmed(self, db, row, ar):
        snap = json.loads(row["snapshot"])
        status = snap["state"].get("status")
        # A run cancelled while its coordinator never accepted the assignment has no runner to report an outcome; the
        # confirmed-stopped processes below are then the whole truth.
        unstarted = status == "STARTING" and (self.store.get(row["run_id"]) or {}).get("cancelRequested")
        if row["released"] or (status not in QUIESCENT and not unstarted):
            return
        for did in ar["deviceIds"]:
            d = db.execute("SELECT processes,seen FROM devices WHERE id=?", (did,)).fetchone()
            reports = [
                p for p in json.loads(d[0]) if p["assignmentId"] == ar["assignmentId"] and p["epoch"] == ar["epoch"]
            ]
            if time.time() - d["seen"] >= 30 or len(reports) != 1:
                return
            p = reports[0]
            if did == ar["coordinatorDeviceId"] and p.get("coordinatorAlive") is not False:
                return
            if did in ar["workerDevices"].values() and p.get("workerAlive") is not False:
                return
        if unstarted:
            snap["state"] = {**snap["state"], "status": "CANCELLED"}
            db.execute("UPDATE assignments SET snapshot=? WHERE id=?", (json.dumps(snap), ar["assignmentId"]))
        db.execute("UPDATE assignments SET released=1 WHERE id=?", (ar["assignmentId"],))
        db.execute("DELETE FROM device_reservations WHERE assignment_id=?", (ar["assignmentId"],))
        db.execute("DELETE FROM physical_reservations WHERE assignment_id=?", (ar["assignmentId"],))
