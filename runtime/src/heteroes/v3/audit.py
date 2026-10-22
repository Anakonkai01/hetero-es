"""Deterministic v3 text audits, using the existing ledger audit transaction.

Operational leases stay outside the numerical ledger. Canonical completed audits
are recovered by reading its audit table under its connection lock; all ledger
writes go through the existing public methods. Audit work uses the current
parent/context and is drained before that generation's numerical update.
"""

from collections import OrderedDict
import hashlib
import math
import secrets
import threading
import time

from heteroes.ledger import LedgerError, FailureKind
from heteroes.product.files import read_json, write_json
from heteroes.worker_api import _decode_lease, _decode_result, _decode_heartbeat, _decode_failure, _error, _code_of


def selected_for_audit(candidate_id, rate=0.05):
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("audit rate must be between zero and one")
    # The default is exactly 1/20 of the SHA-256 address space, not a process RNG.
    threshold = 2**256 // 20 if rate == 0.05 else int(rate * 2**256)
    return int(hashlib.sha256(candidate_id.encode()).hexdigest(), 16) < threshold


class AuditAPI:
    def __init__(
        self,
        base,
        ledger,
        experiment_id,
        generation,
        *,
        rate=0.05,
        workers=None,
        lease_seconds=60,
        clock=time.time,
        fault_path=None,
        log=lambda event: None,
        cancel_requested=lambda: False,
    ):
        selected_for_audit("validate", rate)
        if (
            not isinstance(lease_seconds, (int, float))
            or isinstance(lease_seconds, bool)
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise ValueError("audit lease must be finite and positive")
        self.base, self.ledger = base, ledger
        self.experiment_id, self.generation, self.rate = experiment_id, generation, rate
        self.workers = None if workers is None else frozenset(workers)
        self.lease_seconds, self.clock, self.log = lease_seconds, clock, log
        self.fault_path = fault_path
        self.faults = read_json(fault_path, {}) if fault_path is not None else {}
        self._seen, self._leases, self._requests = set(), {}, OrderedDict()
        self._activity = 0  # audit leases, heartbeats, results and failures (see WorkerAPI.activity)
        self._lock = threading.RLock()
        self.fatal_error = None
        self.cancel_requested = cancel_requested

    @property
    def scoring_error(self):
        return self.base.scoring_error

    @property
    def quarantined_workers(self):
        return set(self.faults) | {q.worker_id for q in self.ledger.list_quarantined()}

    @property
    def activity(self):
        return self.base.activity + self._activity

    def audit_counts(self):
        """(selected, completed): the committed candidates of this generation chosen for re-execution, and how many of
        them another worker re-executed. A timed-out drain leaves completed < selected; the summary shows it (ADR-009)."""
        with self.ledger._lock:
            rows = self.ledger._db.execute(
                "SELECT c.candidate_id, EXISTS (SELECT 1 FROM audit u WHERE u.candidate_id = c.candidate_id) "
                "FROM candidate c JOIN completion t ON t.candidate_id = c.candidate_id "
                "WHERE c.experiment_id = ? AND c.generation = ?",
                (self.experiment_id, self.generation),
            ).fetchall()
        chosen = [bool(done) for cid, done in rows if selected_for_audit(cid, self.rate)]
        return len(chosen), sum(chosen)

    @property
    def available_workers(self):
        return (self._seen if self.workers is None else self.workers) - self.quarantined_workers

    def _records(self):
        # Read-only projection of the live ledger; no historical WAL files are opened.
        with self.ledger._lock:
            rows = self.ledger._db.execute(
                "SELECT c.candidate_id,a.worker_id FROM candidate c JOIN result r USING(candidate_id) "
                "JOIN attempt a ON a.candidate_id=r.candidate_id AND a.attempt_number=r.attempt_number "
                "JOIN completion t ON t.candidate_id=c.candidate_id "
                "WHERE c.experiment_id=? AND c.generation=? "
                "AND NOT EXISTS (SELECT 1 FROM audit u WHERE u.candidate_id=c.candidate_id) ORDER BY c.candidate_index",
                (self.experiment_id, self.generation),
            ).fetchall()
        return [(cid, original) for cid, original in rows if selected_for_audit(cid, self.rate)]

    @property
    def pending(self):
        with self._lock:
            return len(self._records())

    def handle(self, operation, request, authenticated_worker_id=None):
        with self._lock:
            try:
                if isinstance(request, dict) and "audit_id" in request:
                    return self._audit(operation, request, authenticated_worker_id)
                if operation != "lease":
                    return self.base.handle(operation, request, authenticated_worker_id=authenticated_worker_id)
                worker, request_id, generation = _decode_lease(request)
                if authenticated_worker_id is not None and worker != authenticated_worker_id:
                    return _error("forbidden", "Credential does not own this worker")
                if self.workers is not None and worker not in self.workers:
                    return _error("forbidden", "Worker was not admitted for this run")
                if worker in self.quarantined_workers:
                    return _error("worker_quarantined", "Worker is quarantined")
                self._seen.add(worker)
                reply = self.base.handle(operation, request, authenticated_worker_id=authenticated_worker_id)
                if (
                    not reply["ok"]
                    or reply.get("work") is not None
                    or self.cancel_requested()
                    or (generation is not None and generation != self.generation)
                ):
                    return reply
                work = self._lease(worker, request_id, request.get("max_chunk"))
                return {
                    "ok": True,
                    "generation_state": "OPEN" if work or self.pending else reply["generation_state"],
                    "work": work,
                }
            except (TypeError, ValueError, KeyError) as error:
                return _error("bad_request", str(error))
            except LedgerError as error:
                return _error(_code_of(error), str(error))

    def _lease(self, worker, request_id, max_chunk=None):
        now = self.clock()
        if request_id is not None:
            cid = self._requests.get((worker, request_id))
            entry = self._leases.get(cid)
            if entry and entry["worker"] == worker and not entry["done"] and entry["work"]["deadline"] > now:
                return dict(entry["work"])
        for cid, original in self._records():
            if original == worker:
                continue
            # ADR-010: re-run at the chunk the result used, by a worker that may use it (else it fails for memory)
            chunk = self.ledger.completion_chunk(cid)
            if chunk is not None and (max_chunk is None or chunk > max_chunk):
                continue
            entry = self._leases.get(cid)
            if entry and not entry["done"] and entry["work"]["deadline"] > now:
                continue
            descriptor = self.ledger.get_candidate(cid).descriptor
            number = 1 if entry is None else entry["work"]["attempt_number"] + 1
            work = {
                "descriptor": descriptor.to_dict(),
                "attempt_number": number,
                "token": secrets.token_urlsafe(32),
                "deadline": now + self.lease_seconds,
                "audit_id": hashlib.sha256(cid.encode()).hexdigest(),
                **({"chunk": chunk} if chunk is not None else {}),
            }
            self._leases[cid] = {"worker": worker, "work": work, "done": False, "hash": None}
            if request_id is not None:
                self._requests[worker, request_id] = cid
                while len(self._requests) > 256:
                    self._requests.popitem(last=False)
            self.log(
                {"event": "audit_leased", "candidate_id": cid, "worker_id": worker, "original_worker_id": original}
            )
            self._activity += 1
            return dict(work)
        return None

    def _audit(self, operation, request, authenticated_worker_id):
        decoders = {"submit_result": _decode_result, "heartbeat": _decode_heartbeat, "report_failure": _decode_failure}
        if operation not in decoders:
            return _error("bad_request", "Unsupported audit operation")
        body = {k: v for k, v in request.items() if k != "audit_id"}
        decoded = decoders[operation](body)
        descriptor, number, token = decoded[:3]
        if operation == "submit_result" and "completions" not in body:
            return _error("bad_request", "Audits require completions, not rewards")
        entry = self._leases.get(descriptor.candidate_id)
        if entry is None:
            return _error("stale_attempt", "No audit lease for this candidate")
        if authenticated_worker_id is not None and authenticated_worker_id != entry["worker"]:
            return _error("forbidden", "Credential does not own this audit")
        work = entry["work"]
        if (
            descriptor.to_dict() != work["descriptor"]
            or number != work["attempt_number"]
            or not secrets.compare_digest(token, work["token"])
            or request["audit_id"] != work["audit_id"]
        ):
            return _error("stale_attempt", "Audit identity differs from the lease")
        if entry["done"]:
            if operation == "submit_result" and body["completions_sha256"] == entry["hash"]:
                self.base.record_usage(descriptor, number, entry["worker"], getattr(decoded[3], "usage", None), "audit")
                return {
                    "ok": True,
                    "outcome": "ALREADY_COMMITTED",
                    "matched": entry["matched"],
                    "quarantined_workers": sorted(self.quarantined_workers),
                }
            return _error("conflicting_result", "Completed audit cannot change")
        worker = entry["worker"]
        if worker in self.quarantined_workers:
            return _error("worker_quarantined", "Worker is quarantined")
        self._activity += 1
        if operation == "heartbeat":
            work["deadline"] = self.clock() + self.lease_seconds
            return {"ok": True, "deadline": work["deadline"]}
        if operation == "report_failure":
            work["deadline"] = 0
            kind = decoded[3]
            self.log(
                {
                    "event": "audit_execution_failed",
                    "candidate_id": descriptor.candidate_id,
                    "worker_id": worker,
                    "failure": kind.value,
                }
            )
            if kind is FailureKind.RESTORE_MISMATCH:
                self.faults[worker] = {"reason": kind.value, "candidateId": descriptor.candidate_id}
                if self.fault_path is not None:
                    write_json(self.fault_path, self.faults)
                self.fatal_error = "Audit worker failed exact restore"
                return _error("worker_quarantined", self.fatal_error)
            return {"ok": True}
        digest = body["completions_sha256"]
        matched = self.ledger.record_audit(descriptor.candidate_id, worker, digest)
        self.base.record_usage(descriptor, number, worker, getattr(decoded[3], "usage", None), "audit")
        entry.update(done=True, hash=digest, matched=matched)
        self.log(
            {
                "event": "audit_completed" if matched else "audit_mismatch",
                "candidate_id": descriptor.candidate_id,
                "worker_id": worker,
                "matched": matched,
            }
        )
        quarantined = sorted(self.quarantined_workers)
        for name in quarantined:
            self.log({"event": "audit_worker_quarantined", "worker_id": name, "reason": "AUDIT_MISMATCH"})
        return {"ok": True, "outcome": "COMMITTED", "matched": matched, "quarantined_workers": quarantined}
