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

# A worker that left and whose device has not been seen for this long counts as stopped: it cannot confirm the stop while
# offline, and waiting for it held every device of a finished run (GSM8K demo tier 2, 2026-10-21).
LEFT_OFFLINE_RELEASE_SECONDS = 600


class AgentScheduling:
    def waiting_reason(self, body, db=None, workers=None):
        """Why `body` cannot start yet, or None. `workers` checks only those (a worker joining a running run, ADR-009)."""
        if db is None:
            with self.store.db() as connection:
                return self.waiting_reason(body, connection, workers)
        devices = self.devices(db)
        by_id = {d["deviceId"]: d for d in devices}
        by_worker = {d["workerId"]: d for d in devices}
        coordinator = by_id.get(body.get("coordinatorDeviceId"))
        if not coordinator or not coordinator["selfTest"].get("coordinator"):
            return "Select an approved coordinator device"
        selected = (
            workers if workers is not None else self.intended_members(db, body["experimentId"], body["workerIds"])
        )
        chosen = [coordinator] + [by_worker.get(w) for w in selected]
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
        workers = [by_worker[w]["physicalResourceId"] for w in selected]
        if len(set(workers)) != len(workers):
            return "Selected worker aliases refer to the same physical GPU"
        return None

    def intended_members(self, db, run_id, initial):
        """The workers a run should have (ADR-009): the submitted ones, then every requested join and leave, in order."""
        members = list(initial)
        rows = db.execute("SELECT worker_id, action FROM assignment_members WHERE run_id=? ORDER BY rowid", (run_id,))
        for worker_id, action in rows:
            if action == "JOIN" and worker_id not in members:
                members.append(worker_id)
            elif action == "LEAVE" and worker_id in members:
                members.remove(worker_id)
        return members

    def change_members(self, db, run_id, worker_id, action, actor):
        """
        A worker joins or leaves a running experiment (elastic membership, ADR-009). A join passes the same checks as a
        submission, reserves the device and its GPU and gives the worker its own credential; the coordinator applies the
        change at its next generation boundary and records it in its ledger. The frozen configuration never changes.
        """
        body = self.store.get(run_id)
        row = db.execute("SELECT * FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (run_id,)).fetchone()
        if not body or body["status"] not in ("STARTING", "RUNNING") or not row or row["released"]:
            raise RuntimeRejected("Members change only while the experiment is running")
        self.require_command(db, row["coordinator"], "UPDATE_MEMBERSHIP")
        ar = json.loads(row["body"])
        members = self.intended_members(db, run_id, body["workerIds"])
        change = {"changeId": uuid.uuid4().hex, "workerId": worker_id, "action": action, "actor": actor}
        if action == "JOIN":
            if worker_id in members:
                raise RuntimeRejected("The worker is already a member")
            devices = {d["workerId"]: d for d in self.devices(db)}
            if worker_id not in devices:
                raise RuntimeRejected("Select an approved worker device")
            device = devices[worker_id]
            if db.execute("SELECT 1 FROM device_reservations WHERE device_id=?", (device["deviceId"],)).fetchone():
                raise RuntimeRejected("Waiting for confirmed GPU release")  # busy elsewhere, or still leaving this run
            if reason := self.waiting_reason(body, db, [worker_id]) or self.store.eligibility(db, body, [worker_id]):
                raise RuntimeRejected(reason)
            if device["physicalResourceId"] in {devices[m]["physicalResourceId"] for m in members if m in devices}:
                raise RuntimeRejected("Selected worker aliases refer to the same physical GPU")
            change["grant"] = ar["computeGrants"][worker_id] = secrets.token_urlsafe(32)
            ar["workerDevices"][worker_id] = device["deviceId"]
            if device["deviceId"] not in ar["deviceIds"]:
                ar["deviceIds"].append(device["deviceId"])
            db.execute("UPDATE assignments SET body=? WHERE id=?", (json.dumps(ar), row["id"]))
            db.execute("INSERT INTO device_reservations VALUES (?,?)", (device["deviceId"], row["id"]))
            if device["physicalResourceId"]:
                db.execute("INSERT INTO physical_reservations VALUES (?,?)", (device["physicalResourceId"], row["id"]))
            device_id = device["deviceId"]
        elif action == "LEAVE":
            if worker_id not in members:
                raise RuntimeRejected("The worker is not a member")
            if len(members) == 1:
                raise RuntimeRejected("The last member cannot leave")
            device_id = ar["workerDevices"].get(worker_id, "")
        else:
            raise RuntimeRejected("A member joins or leaves")
        db.execute(
            "INSERT INTO assignment_members VALUES (?,?,?,?,?,?,?)",
            (change["changeId"], run_id, worker_id, device_id, action, actor, time.time()),
        )
        self.enqueue(
            db,
            row["coordinator"],
            "UPDATE_MEMBERSHIP",
            {"assignmentId": row["id"], "epoch": row["epoch"], "change": change},
            "membership:" + change["changeId"],
        )
        return {key: value for key, value in change.items() if key != "grant"}

    def note_membership(self, db, run_id, change, actor_id):
        """Keep the request on the experiment for the lab's pages and audit it; the coordinator's view arrives later."""
        body = self.store.get(run_id)
        body.setdefault("membershipRequests", []).append({**change, "requestedAt": time.time()})
        self.store.save(db, body)
        self.store.audit(db, actor_id, f"MEMBERSHIP_{change['action']}_REQUESTED", run_id, body["workspaceId"])

    def _try_change(self, db, run_id, worker_id, action):
        try:
            change = self.change_members(db, run_id, worker_id, action, "system")
        except (RuntimeRejected, HTTPException):
            return False
        self.note_membership(db, run_id, change, "system")
        return True

    def auto_join(self, db, body):
        """An experiment that allows joining takes every idle eligible worker of its workspace, except one that has
        already left it (an owner who removed a worker means it)."""
        if not body.get("allowJoin") or body["status"] not in ("STARTING", "RUNNING"):
            return
        run_id = body["experimentId"]
        members = set(self.intended_members(db, run_id, body["workerIds"]))
        left = {
            r[0]
            for r in db.execute("SELECT worker_id FROM assignment_members WHERE run_id=? AND action='LEAVE'", (run_id,))
        }
        workspace = {
            r[0]
            for r in db.execute("SELECT worker_id FROM worker_assignments WHERE workspace_id=?", (body["workspaceId"],))
        }
        for worker_id in sorted(workspace - members - left):
            self._try_change(db, run_id, worker_id, "JOIN")

    def leave_on_disable(self, db, device):
        """The owner turned a worker OFF: in a running experiment that has other members it leaves at the next boundary
        instead of cancelling everyone's work (ADR-009). Returns the runs it left; the caller cancels the others."""
        left = set()
        for (run_id,) in db.execute(
            "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id "
            "WHERE r.device_id=? AND a.released=0 AND a.coordinator!=?",
            (device["id"], device["id"]),
        ).fetchall():
            body = self.store.get(run_id)
            members = self.intended_members(db, run_id, body["workerIds"]) if body else []
            if (
                device["worker_id"] in members
                and len(members) > 1
                and self._try_change(db, run_id, device["worker_id"], "LEAVE")
            ):
                left.add(run_id)
        return left

    def release_left_members(self, db, row, snapshot):
        """A worker that left and that the coordinator confirms stopped gives its device and GPU back at once (ADR-009);
        it no longer counts for the final release of this assignment."""
        left = set((snapshot.get("membership") or {}).get("left", []))
        # one added back after it left stays "left" in the coordinator's reports until its next boundary
        experiment = db.execute("SELECT body FROM experiments WHERE id=?", (row["run_id"],)).fetchone()
        initial = json.loads(experiment[0])["workerIds"] if experiment else []
        left -= set(self.intended_members(db, row["run_id"], initial))
        states = (snapshot.get("state") or {}).get("workerStates", {})
        ar = json.loads(row["body"])
        changed = False
        for worker_id in sorted(left):
            state = states.get(worker_id) or {}
            device_id = ar["workerDevices"].get(worker_id)
            if device_id is None:
                continue
            resource = db.execute("SELECT self_test,seen FROM devices WHERE id=?", (device_id,)).fetchone()
            gone = (
                resource is not None
                and device_id != ar["coordinatorDeviceId"]
                and time.time() - resource["seen"] >= LEFT_OFFLINE_RELEASE_SECONDS
            )
            if not (state.get("left") or (state.get("confirmed") and state.get("alive") is False) or gone):
                continue
            gpu = json.loads(resource[0]).get("gpuUUID") if resource else None
            db.execute("DELETE FROM device_reservations WHERE device_id=? AND assignment_id=?", (device_id, row["id"]))
            if gpu:
                db.execute(
                    "DELETE FROM physical_reservations WHERE resource_id=? AND assignment_id=?", (gpu, row["id"])
                )
            ar["workerDevices"].pop(worker_id)
            ar["computeGrants"].pop(worker_id, None)
            if device_id not in ar["workerDevices"].values() and device_id != ar["coordinatorDeviceId"]:
                ar["deviceIds"] = [d for d in ar["deviceIds"] if d != device_id]
            changed = True
        if changed:
            db.execute("UPDATE assignments SET body=? WHERE id=?", (json.dumps(ar), row["id"]))

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
            members = self.intended_members(db, config["runId"], config["workerIds"])
            chosen = {d["deviceId"]: d for d in [co] + [by_worker[w] for w in members]}
            aid = uuid.uuid4().hex
            # Secrets are random per device/run, stored only in the private product DB.
            grants = {d["workerId"]: secrets.token_urlsafe(32) for d in chosen.values() if d["workerId"] in members}
            assignment = {
                "assignmentId": aid,
                "runId": config["runId"],
                "coordinatorDeviceId": co["deviceId"],
                "epoch": old["epoch"] + 1 if old else 1,
                "deviceIds": list(chosen),
                "config": config,
                "computeUrl": co["computeUrl"],
                "bulkUrl": co["bulkUrl"],
                "workerDevices": {w: by_worker[w]["deviceId"] for w in members},
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
