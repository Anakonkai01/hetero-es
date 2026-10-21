"""CPU-only device control. Connectivity is never evidence of process death."""

from .constants import CORE_COMMAND_KINDS, COMMAND_KINDS

import re
import json
import time

from fastapi import HTTPException

from .constants import QUIESCENT


from .device_models import digest
from heteroes.product.cpu_coordinator import coordinator_only


class AgentPolling:
    def poll(self, device, body, command_kinds=CORE_COMMAND_KINDS):
        with self.store.db() as db:
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES (?,?)",
                ("agentCommands:" + device["id"], json.dumps(sorted(command_kinds))),
            )
            old = db.execute("SELECT * FROM devices WHERE id=?", (device["id"],)).fetchone()
            self._refresh_observation(db, device, body, old)
            desired = self._update_boot(db, device, body, old)
            self._quarantine_processes(db, device, body, old)
            accepted_events = self._accept_events(db, device, body, old)
            accepted = self._accept_reports(db, device, body, old)
            accepted_qualifications = self.qualifications.accept(db, device, body.qualificationReports)
            for row in db.execute("SELECT * FROM assignments WHERE released=0").fetchall():
                self._release_confirmed(db, row, json.loads(row["body"]))
            old = db.execute("SELECT * FROM devices WHERE id=?", (device["id"],)).fetchone()
            allowed = old["status"] == "APPROVED" and self.store.profile(old["owner"])["accountStatus"] == "ACTIVE"
            commands = self.commands(device["id"], command_kinds=command_kinds)
            if not allowed:
                commands = [
                    c
                    for c in commands
                    if c["kind"] in ("CANCEL_ASSIGNMENT", "STOP_WORKER", "CANCEL_MODEL_QUALIFICATION")
                ]
            # Previously accepted assignments must remain recoverable even after OFF;
            # the agent adopts living processes but gates every new launch locally.
            return {
                "deviceId": device["id"],
                "approvalStatus": old["status"],
                "desiredContribution": bool(desired and allowed),
                "commands": commands[:100],
                "acceptedReports": accepted,
                "acceptedQualifications": accepted_qualifications,
                "acceptedEvents": accepted_events,
                "heartbeatSeconds": 10,
                "telemetrySupported": True,
                "detailedTelemetrySupported": True,
                "modelQualificationSupported": True,
                "releasedAssignments": [
                    row["id"]
                    for row in db.execute("SELECT id,body FROM assignments WHERE released=1")
                    if device["id"] in json.loads(row["body"])["deviceIds"]
                ],
            }

    def _refresh_observation(self, db, device, body, old):
        if body.selfTest is not None:
            previous = json.loads(old["self_test"])
            updated = body.selfTest.model_dump()
            from .policies import has_device_reservation

            reserved = has_device_reservation(db, device["id"], previous.get("gpuUUID"))
            if reserved and (
                updated.get("gpuUUID") != previous.get("gpuUUID")
                or coordinator_only(updated) != coordinator_only(previous)
            ):
                raise HTTPException(409, "Physical GPU identity cannot change during ownership")
            if not updated["passed"]:
                raise HTTPException(422, "Self-test refresh must pass qualification")
            db.execute("UPDATE devices SET self_test=? WHERE id=?", (json.dumps(updated), device["id"]))
        if body.telemetry is not None:
            observation = body.telemetry.model_dump(exclude_none=True)
            profile = json.loads(old["self_test"])
            if observation.get("gpu") and profile.get("gpuUUID") and observation["gpu"]["uuid"] != profile["gpuUUID"]:
                raise HTTPException(422, "Telemetry GPU differs from qualified physical GPU")
            observation["receivedAt"] = time.time()
            db.execute("UPDATE devices SET telemetry=? WHERE id=?", (json.dumps(observation), device["id"]))
            gpu = observation.get("gpu", {})
            host = observation.get("host", {})
            power = observation.get("power") or {}
            packages = [
                c["powerW"]
                for c in power.get("components", [])
                if c["kind"] == "cpu-package" and c.get("powerW") is not None
            ]
            point = {
                "at": observation["receivedAt"],
                "cpuPowerW": sum(packages) if packages else None,
                "componentPowerW": power.get("componentSubtotalW"),
                "wholeMachineW": power.get("wholeMachineW"),
                "gpuPowerW": gpu.get("powerDrawW"),
                "temperatureC": gpu.get("temperatureC"),
                "gpuPercent": gpu.get("utilizationPercent"),
                "cpuPercent": host.get("cpuPercent"),
                "vramUsedMb": gpu.get("vramUsedMb"),
                "ramUsedBytes": host.get("ramUsedBytes"),
            }
            db.execute(
                "INSERT OR IGNORE INTO device_telemetry_history VALUES (?,?,?,?,?)",
                (device["id"], body.bootId, observation["sampledAt"], observation["receivedAt"], json.dumps(point)),
            )
            db.execute(
                "DELETE FROM device_telemetry_history WHERE device_id=? AND rowid NOT IN (SELECT rowid FROM device_telemetry_history WHERE device_id=? ORDER BY received_at DESC LIMIT 180)",
                (device["id"], device["id"]),
            )
        elif old["boot_id"] != body.bootId:
            db.execute("UPDATE devices SET telemetry=NULL WHERE id=?", (device["id"],))

    def _update_boot(self, db, device, body, old):
        changed = old["boot_id"] != body.bootId
        desired = 0 if changed else old["desired"]
        # ON must be requested through owner auth and observed on this same boot.
        enabled = bool(desired and body.contribution)
        db.execute(
            "UPDATE devices SET boot_id=?,seen=?,enabled=?,desired=?,processes=? WHERE id=?",
            (
                body.bootId,
                time.time(),
                enabled,
                desired,
                json.dumps([p.model_dump() for p in body.processes]),
                device["id"],
            ),
        )
        if changed:
            db.execute(
                "UPDATE device_commands SET ack=1 WHERE device_id=? AND json_extract(body,'$.kind')='SET_CONTRIBUTION'",
                (device["id"],),
            )
            # Cancellation remains authoritative across agent boots, including
            # when an old boot acknowledged it before a process-state report.
            for assignment in db.execute(
                "SELECT a.* FROM assignments a JOIN device_reservations r ON r.assignment_id=a.id WHERE r.device_id=?",
                (device["id"],),
            ).fetchall():
                run = self.store.get(assignment["run_id"])
                if run and run.get("cancelRequested"):
                    self.enqueue(
                        db,
                        device["id"],
                        "CANCEL_ASSIGNMENT",
                        {"assignmentId": assignment["id"], "epoch": assignment["epoch"]},
                        f"cancel-boot:{assignment['id']}:{device['id']}:{body.bootId}",
                    )
        for cid in body.acknowledgements:
            db.execute("UPDATE device_commands SET ack=1 WHERE id=? AND device_id=?", (cid, device["id"]))
        return desired

    def _quarantine_processes(self, db, device, body, old):
        for process in body.processes:
            if any(
                event.get("failure") == "RESTORE_MISMATCH" or event.get("reason") == "quarantined"
                for event in process.events
            ):
                db.execute("UPDATE devices SET status=?,enabled=0,desired=0 WHERE id=?", ("QUARANTINED", device["id"]))
                self.store.cancel_selected(db, old["worker_id"])
                for assignment in db.execute(
                    "SELECT a.run_id FROM assignments a JOIN device_reservations r ON a.id=r.assignment_id WHERE r.device_id=?",
                    (device["id"],),
                ).fetchall():
                    self.cancel(assignment["run_id"], db=db)
                self.store.audit(db, "system", "DEVICE_RESTORE_MISMATCH", device["id"])

    def _accept_events(self, db, device, body, old):
        accepted_events = []
        for event in body.events:
            assignment = db.execute(
                "SELECT coordinator,epoch FROM assignments WHERE id=?", (event.assignmentId,)
            ).fetchone()
            encoded = json.dumps(event.event, sort_keys=True, separators=(",", ":"), allow_nan=False)
            expected = digest(event.assignmentId + encoded)
            if (
                assignment
                and (assignment["coordinator"], assignment["epoch"]) == (device["id"], event.epoch)
                and event.eventId == expected
            ):
                inserted = db.execute(
                    "INSERT OR IGNORE INTO monitoring_events(event_id,assignment_id,body) VALUES (?,?,?)",
                    (event.eventId, event.assignmentId, encoded),
                ).rowcount
                accepted_events.append(event.eventId)
                if (
                    inserted
                    and event.event.get("event") == "audit_worker_quarantined"
                    and event.event.get("reason") == "AUDIT_MISMATCH"
                ):
                    row = db.execute(
                        "SELECT body,released FROM assignments WHERE id=?", (event.assignmentId,)
                    ).fetchone()
                    ar = json.loads(row["body"])
                    target = ar.get("workerDevices", {}).get(event.event.get("worker_id"))
                    if target and not row["released"] and ar["config"].get("recipeVersion") == 3:
                        changed = db.execute(
                            "UPDATE devices SET status='QUARANTINED',enabled=0,desired=0 WHERE id=? AND status='APPROVED'",
                            (target,),
                        ).rowcount
                        if changed:
                            self.store.cancel_selected(db, event.event["worker_id"])
                            self.store.audit(db, "system", "DEVICE_AUDIT_MISMATCH", target)
        return accepted_events

    def _accept_reports(self, db, device, body, old):
        accepted = []
        for report in body.reports:
            row = db.execute("SELECT * FROM assignments WHERE id=?", (report.assignmentId,)).fetchone()
            if not row or row["coordinator"] != device["id"] or row["epoch"] != report.epoch:
                continue
            if len(json.dumps(report.snapshot)) > 2_000_000:
                raise HTTPException(413, "Snapshot is too large")
            if report.snapshot.get("state", {}).get("status") not in QUIESCENT | {
                "STARTING",
                "RUNNING",
                "CANCELLING",
                "RECOVERING",
                "DRAINING",
                "PAUSING",
            }:
                raise HTTPException(422, "Invalid runtime status")
            if report.snapshot["state"]["status"] == "PAUSED":
                point = report.snapshot["state"].get("pauseCheckpoint", {})
                if (
                    point.get("verified") is not True
                    or type(point.get("generation")) is not int
                    or point["generation"] < 0
                    or not re.fullmatch("[a-f0-9]{32}", str(point.get("pointId", "")))
                    or any(
                        not re.fullmatch("[a-f0-9]{64}", str(point.get(k, "")))
                        for k in ("childWeightsSha256", "parentWeightsSha256")
                    )
                ):
                    raise HTTPException(422, "Pause requires a verified completed checkpoint")
            if any(
                not isinstance(report.snapshot.get(k), list)
                for k in ("generations", "candidates", "attempts", "events", "artifacts")
            ):
                raise HTTPException(422, "Invalid runtime snapshot")
            accepted.append({"assignmentId": report.assignmentId, "sequence": report.sequence})
            already = db.execute(
                "SELECT 1 FROM device_reports WHERE device_id=? AND assignment_id=? AND sequence=?",
                (device["id"], report.assignmentId, report.sequence),
            ).fetchone()
            if already:
                continue
            maximum = (
                db.execute(
                    "SELECT max(sequence) FROM device_reports WHERE device_id=? AND assignment_id=?",
                    (device["id"], report.assignmentId),
                ).fetchone()[0]
                or 0
            )
            db.execute(
                "INSERT INTO device_reports VALUES (?,?,?)", (device["id"], report.assignmentId, report.sequence)
            )
            if report.sequence > maximum and not row["released"]:
                db.execute(
                    "UPDATE assignments SET snapshot=? WHERE id=?",
                    (json.dumps(report.snapshot, allow_nan=False), report.assignmentId),
                )
                self.release_left_members(db, row, report.snapshot)  # a worker that left gives its GPU back
            elif report.sequence > maximum and row["released"]:
                # A completed assignment can still finish artifact/event sync.
                # Its terminal state and numerical lineage remain immutable.
                cached = self.store.snapshot(row["run_id"])
                latest = db.execute(
                    "SELECT id FROM assignments WHERE run_id=? ORDER BY epoch DESC LIMIT 1", (row["run_id"],)
                ).fetchone()[0]
                if latest == row["id"] and cached and "artifactContents" in report.snapshot:
                    cached["artifactContents"] = report.snapshot["artifactContents"]
                    db.execute(
                        "UPDATE experiments SET snapshot=? WHERE id=?",
                        (json.dumps(cached, allow_nan=False), row["run_id"]),
                    )
        return accepted
