"""CPU-only device control. Connectivity is never evidence of process death."""

from backend.core.constants import CORE_COMMAND_KINDS as CORE_COMMAND_KINDS, COMMAND_KINDS as COMMAND_KINDS

import re
import json
import time

from ..core.errors import ServiceError
from ..repositories.agent_polling import AgentPollingRepository as repository

from backend.core.constants import QUIESCENT as QUIESCENT


from backend.core.device_models import digest as digest
from heteroes.product.cpu_coordinator import coordinator_only


class AgentPolling:
    def poll(self, device, body, command_kinds=CORE_COMMAND_KINDS):
        with self.store.db() as db:
            repository.poll_insert_settings(db, ("agentCommands:" + device["id"], json.dumps(sorted(command_kinds))))
            old = repository.poll_select_devices(db, (device["id"],)).fetchone()
            self._refresh_observation(db, device, body, old)
            desired = self._update_boot(db, device, body, old)
            self._quarantine_processes(db, device, body, old)
            accepted_events = self._accept_events(db, device, body, old)
            accepted = self._accept_reports(db, device, body, old)
            accepted_qualifications = self.qualifications.accept(db, device, body.qualificationReports)
            for row in repository.poll_select_assignments(db, ()).fetchall():
                # a left worker that went offline is released by time, even when its coordinator reports nothing new
                self.release_left_members(db, row, json.loads(row["snapshot"]))
                row = repository.poll_select_assignments_2(db, (row["id"],)).fetchone()
                self._release_confirmed(db, row, json.loads(row["body"]))
            old = repository.poll_select_devices_2(db, (device["id"],)).fetchone()
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
                "metricAvailabilitySupported": True,
                "modelQualificationSupported": True,
                "releasedAssignments": [
                    row["id"]
                    for row in repository.poll_select_assignments_3(db, ())
                    if device["id"] in json.loads(row["body"])["deviceIds"]
                ],
                # processes this device still reports for an assignment that no longer reserves it (its GPU was given
                # back after it left or went offline): the agent stops them before it starts anything else
                "revokedAssignments": sorted(
                    {
                        p.assignmentId
                        for p in body.processes
                        if repository.poll_select_assignments_4(db, (p.assignmentId,)).fetchone()
                        and not repository.poll_select_device_reservations(
                            db, (device["id"], p.assignmentId)
                        ).fetchone()
                    }
                ),
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
                raise ServiceError(409, "Physical GPU identity cannot change during ownership")
            if not updated["passed"]:
                raise ServiceError(422, "Self-test refresh must pass qualification")
            repository._refresh_observation_update_devices(db, (json.dumps(updated), device["id"]))
        if body.telemetry is not None:
            observation = body.telemetry.model_dump(exclude_none=True)
            profile = json.loads(old["self_test"])
            if observation.get("gpu") and profile.get("gpuUUID") and observation["gpu"]["uuid"] != profile["gpuUUID"]:
                raise ServiceError(422, "Telemetry GPU differs from qualified physical GPU")
            observation["receivedAt"] = time.time()
            repository._refresh_observation_update_devices_2(db, (json.dumps(observation), device["id"]))
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
            repository._refresh_observation_insert_device_telemetry_history(
                db, (device["id"], body.bootId, observation["sampledAt"], observation["receivedAt"], json.dumps(point))
            )
            repository._refresh_observation_delete_device_telemetry_history(db, (device["id"], device["id"]))
        elif old["boot_id"] != body.bootId:
            repository._refresh_observation_update_devices_3(db, (device["id"],))

    def _update_boot(self, db, device, body, old):
        changed = old["boot_id"] != body.bootId
        desired = old["keep_on"] if changed else old["desired"]
        # ON is requested for this same boot (by the owner, the device itself, or the owner's keep-after-reboot choice).
        enabled = bool(desired and body.contribution)
        repository._update_boot_update_devices(
            db,
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
            repository._update_boot_update_device_commands(db, (device["id"],))
            if old["keep_on"]:
                # the owner chose to keep contributing after a restart: this new boot is turned ON like the last one
                self.enqueue(
                    db,
                    device["id"],
                    "SET_CONTRIBUTION",
                    {"enabled": True, "bootId": body.bootId},
                    f"keep-on:{device['id']}:{body.bootId}",
                )
            # Cancellation remains authoritative across agent boots, including
            # when an old boot acknowledged it before a process-state report.
            for assignment in repository._update_boot_select_assignments(db, (device["id"],)).fetchall():
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
            repository._update_boot_update_device_commands_2(db, (cid, device["id"]))
        return desired

    def _quarantine_processes(self, db, device, body, old):
        for process in body.processes:
            if any(
                event.get("failure") == "RESTORE_MISMATCH" or event.get("reason") == "quarantined"
                for event in process.events
            ):
                repository._quarantine_processes_update_devices(db, ("QUARANTINED", device["id"]))
                self.store.cancel_selected(db, old["worker_id"])
                for assignment in repository._quarantine_processes_select_assignments(db, (device["id"],)).fetchall():
                    self.cancel(assignment["run_id"], db=db)
                self.store.audit(db, "system", "DEVICE_RESTORE_MISMATCH", device["id"])

    def _accept_events(self, db, device, body, old):
        accepted_events = []
        for event in body.events:
            assignment = repository._accept_events_select_assignments(db, (event.assignmentId,)).fetchone()
            encoded = json.dumps(event.event, sort_keys=True, separators=(",", ":"), allow_nan=False)
            expected = digest(event.assignmentId + encoded)
            if (
                assignment
                and (assignment["coordinator"], assignment["epoch"]) == (device["id"], event.epoch)
                and event.eventId == expected
            ):
                inserted = repository._accept_events_insert_monitoring_events(
                    db, (event.eventId, event.assignmentId, encoded)
                ).rowcount
                accepted_events.append(event.eventId)
                if (
                    inserted
                    and event.event.get("event") == "audit_worker_quarantined"
                    and event.event.get("reason") == "AUDIT_MISMATCH"
                ):
                    row = repository._accept_events_select_assignments_2(db, (event.assignmentId,)).fetchone()
                    ar = json.loads(row["body"])
                    target = ar.get("workerDevices", {}).get(event.event.get("worker_id"))
                    if target and not row["released"] and ar["config"].get("recipeVersion") == 3:
                        changed = repository._accept_events_update_devices(db, (target,)).rowcount
                        if changed:
                            self.store.cancel_selected(db, event.event["worker_id"])
                            self.store.audit(db, "system", "DEVICE_AUDIT_MISMATCH", target)
        return accepted_events

    def _accept_reports(self, db, device, body, old):
        accepted = []
        for report in body.reports:
            row = repository._accept_reports_select_assignments(db, (report.assignmentId,)).fetchone()
            if not row or row["coordinator"] != device["id"] or row["epoch"] != report.epoch:
                continue
            if len(json.dumps(report.snapshot)) > 2_000_000:
                raise ServiceError(413, "Snapshot is too large")
            if report.snapshot.get("state", {}).get("status") not in QUIESCENT | {
                "STARTING",
                "RUNNING",
                "CANCELLING",
                "RECOVERING",
                "DRAINING",
                "PAUSING",
            }:
                raise ServiceError(422, "Invalid runtime status")
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
                    raise ServiceError(422, "Pause requires a verified completed checkpoint")
            if any(
                not isinstance(report.snapshot.get(k), list)
                for k in ("generations", "candidates", "attempts", "events", "artifacts")
            ):
                raise ServiceError(422, "Invalid runtime snapshot")
            accepted.append({"assignmentId": report.assignmentId, "sequence": report.sequence})
            already = repository._accept_reports_select_device_reports(
                db, (device["id"], report.assignmentId, report.sequence)
            ).fetchone()
            if already:
                continue
            maximum = (
                repository._accept_reports_select_device_reports_2(db, (device["id"], report.assignmentId)).fetchone()[
                    0
                ]
                or 0
            )
            repository._accept_reports_insert_device_reports(db, (device["id"], report.assignmentId, report.sequence))
            if report.sequence > maximum and not row["released"]:
                repository._accept_reports_update_assignments(
                    db, (json.dumps(report.snapshot, allow_nan=False), report.assignmentId)
                )
                self.release_left_members(db, row, report.snapshot)  # a worker that left gives its GPU back
            elif report.sequence > maximum and row["released"]:
                # A completed assignment can still finish artifact/event sync.
                # Its terminal state and numerical lineage remain immutable.
                cached = self.store.snapshot(row["run_id"])
                latest = repository._accept_reports_select_assignments_2(db, (row["run_id"],)).fetchone()[0]
                if latest == row["id"] and cached and "artifactContents" in report.snapshot:
                    cached["artifactContents"] = report.snapshot["artifactContents"]
                    repository._accept_reports_update_experiments(
                        db, (json.dumps(cached, allow_nan=False), row["run_id"])
                    )
        return accepted
