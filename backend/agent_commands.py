"""CPU-only device control. Connectivity is never evidence of process death."""

from .constants import CORE_COMMAND_KINDS, COMMAND_KINDS

import json
import time
import uuid

from fastapi import HTTPException


class AgentCommands:
    def enqueue(self, db, device_id, kind, body, dedupe):
        cid = uuid.uuid4().hex
        message = {"commandId": cid, "kind": kind, **body}
        db.execute(
            "INSERT OR IGNORE INTO device_commands VALUES (?,?,?,?,0,?)",
            (cid, device_id, dedupe, json.dumps(message, allow_nan=False), time.time()),
        )

    def require_command(self, db, device_id, kind):
        row = db.execute("SELECT value FROM settings WHERE key=?", ("agentCommands:" + device_id,)).fetchone()
        capabilities = json.loads(row[0]) if row else CORE_COMMAND_KINDS
        if kind not in capabilities:
            raise HTTPException(409, "Update the device agent to support " + kind)

    def commands(self, device_id, command_kinds=None):
        with self.store.db() as db:
            result = []
            for row in db.execute(
                "SELECT body FROM device_commands WHERE device_id=? AND ack=0 ORDER BY created", (device_id,)
            ):
                command = json.loads(row[0])
                if command_kinds is not None and command["kind"] not in command_kinds:
                    continue
                if command["kind"] in ("COORDINATE", "START_WORKER", "PAUSE_ASSIGNMENT", "UPDATE_BACKUP_POLICY"):
                    assignment = db.execute(
                        "SELECT released FROM assignments WHERE id=? AND epoch=?",
                        (command["assignmentId"], command["epoch"]),
                    ).fetchone()
                    if not assignment or assignment["released"]:
                        continue
                result.append(command)
            return result

    def worker_command(self, device, body):
        with self.store.db() as db:
            row, ar = self._assignment(db, body.assignmentId)
            if (
                row["coordinator"] != device["id"]
                or row["epoch"] != body.epoch
                or body.workerId not in ar["workerDevices"]
                or row["released"]
            ):
                raise HTTPException(403, "Device is not authorized for this assignment")
            did = ar["workerDevices"][body.workerId]
            target = db.execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone()
            reports = [
                p
                for p in json.loads(target["processes"])
                if p["assignmentId"] == row["id"]
                and p["epoch"] == row["epoch"]
                and p["recoveryIndex"] == body.recoveryIndex
            ]
            if body.action == "start":
                self.enqueue(
                    db,
                    did,
                    "START_WORKER",
                    {
                        "assignmentId": row["id"],
                        "epoch": row["epoch"],
                        "runId": row["run_id"],
                        "workerId": body.workerId,
                        "recoveryIndex": body.recoveryIndex,
                        "coordinatorUrl": ar["computeUrl"],
                        "bulkUrl": ar.get("bulkUrl", ar["computeUrl"]),
                        **({"studyConfig": ar["config"]} if ar["config"].get("recipeVersion") in (2, 3) else {}),
                        "computeToken": ar["computeGrants"][body.workerId],
                        **({"publicComputeUrl": self.public_compute_url()} if self.public_compute_url() else {}),
                    },
                    f"worker:{row['id']}:{did}:{body.recoveryIndex}",
                )
            elif body.action == "stop":
                self.enqueue(
                    db,
                    did,
                    "STOP_WORKER",
                    {"assignmentId": row["id"], "epoch": row["epoch"], "recoveryIndex": body.recoveryIndex},
                    f"stop:{row['id']}:{did}:{body.recoveryIndex}",
                )
            if body.action in ("start", "stop") and (time.time() - target["seen"] >= 30 or not reports):
                return {"alive": None, "ready": False, "events": []}
            if time.time() - target["seen"] >= 30:
                raise HTTPException(503, "Worker process state is unknown")
            if body.action == "probe":
                if target["status"] != "APPROVED" or not target["enabled"] or not target["desired"]:
                    raise HTTPException(409, "Worker contribution is OFF")
                return json.loads(target["self_test"])
            if not reports:
                raise HTTPException(503, "Waiting for worker acknowledgement")
            p = reports[0]
            return {"alive": p["workerAlive"], "ready": p["ready"], "events": p["events"]}
