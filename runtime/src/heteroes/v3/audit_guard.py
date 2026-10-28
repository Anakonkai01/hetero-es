"""Run-level audit safety, independent of the generation API and frozen numerical ledger.

Historical decoders keep the historical mismatch policy (three mismatches quarantine a worker). Only the strict
decoder identity (`strict_b22_v1`, ADR-013) promises the same tokens on every supported GPU, so for it a single audit
text mismatch is a fault: ``stop_on_mismatch`` keeps both receipts and admits no further update (D9).
One coordinator owns this guard and shares it with every generation API.
"""

from pathlib import Path
import threading

from heteroes.ledger import LedgerError
from heteroes.manifest import CandidateDescriptor
from heteroes.product.files import read_json, write_json
from heteroes.worker_api import completions_sha256


def strict_stop_for(recipe):
    """True only for a Recipe v3 run whose evaluation decoder is the strict identity; never for a historical one."""
    from heteroes.catalog import STRICT_DECODERS

    evaluation = getattr(recipe, "evaluation", None)
    return isinstance(evaluation, dict) and evaluation.get("decoder") in STRICT_DECODERS


class AuditStopped(RuntimeError):
    """A run fault forbids admitting a further numerical update."""


class AuditRunGuard:
    def __init__(
        self, ledger, experiment_id, *, fault_path=None, stop_path=None, stop_on_mismatch=False, lease_capacity=4096
    ):
        if type(stop_on_mismatch) is not bool:
            raise ValueError("stop_on_mismatch must be a boolean")
        if stop_on_mismatch and stop_path is None:
            raise ValueError("strict audit stop requires durable receipt storage")
        if type(lease_capacity) is not int or lease_capacity < 1:
            raise ValueError("audit lease capacity must be a positive integer")
        self.ledger, self.experiment_id = ledger, experiment_id
        self.fault_path, self.stop_path = fault_path, stop_path
        self.stop_on_mismatch = stop_on_mismatch
        self._lock = threading.RLock()
        # Audit-only request serialization is separate from update admission. Candidate scoring/heartbeats bypass it.
        self.audit_lock = threading.RLock()
        self.audit_leases = {}
        self.lease_capacity = lease_capacity
        self._faults = read_json(fault_path, {}) if fault_path is not None else {}
        if not isinstance(self._faults, dict) or any(
            not isinstance(worker, str)
            or not worker
            or not isinstance(fault, dict)
            or fault.get("reason") != "RESTORE_MISMATCH"
            or not isinstance(fault.get("candidateId"), str)
            or not fault["candidateId"].startswith(f"{experiment_id}/g")
            for worker, fault in self._faults.items()
        ):
            raise ValueError("invalid audit restore faults")
        self._stop = read_json(stop_path) if stop_path is not None else None
        self._stop_saved = False
        if stop_path is not None and Path(stop_path).exists():
            self._validate_stop(self._stop)
            self._stop_saved = True

    def room_for_lease(self):
        """Retain unfinished deliveries across API rotation; evict only terminal ACK receipts when at capacity.

        If all slots are unfinished, issue no more audit work. The normal finite
        drain deadline reports incomplete coverage rather than losing evidence.
        Lease tokens stay private and in memory; they are not restart credentials.
        """
        with self.audit_lock:
            if len(self.audit_leases) >= self.lease_capacity:
                done = next((cid for cid, entry in self.audit_leases.items() if entry["done"]), None)
                if done is not None:
                    del self.audit_leases[done]
            return len(self.audit_leases) < self.lease_capacity

    @property
    def faults(self):
        with self._lock:
            return dict(self._faults)

    @property
    def fatal_error(self):
        with self._lock:
            if self._stop is not None:
                return "Audit text mismatch requires operator review"
            if self._faults:
                return "Audit worker failed exact restore"
            return None

    def record_update(self, record):
        """Linearize fault observation with admission. An already recorded update is never rolled back."""
        if record.experiment_id != self.experiment_id:
            raise ValueError("audit guard belongs to another experiment")
        with self._lock:
            error = self.fatal_error
            if error:
                raise AuditStopped(error)
            return self.ledger.record_update(record)

    def record_restore_fault(self, worker, candidate_id):
        with self._lock:
            self._faults[worker] = {"reason": "RESTORE_MISMATCH", "candidateId": candidate_id}
            if self.fault_path is not None:
                write_json(self.fault_path, self._faults)

    def _original(self, descriptor):
        if descriptor.experiment_id != self.experiment_id:
            raise ValueError("audit guard belongs to another experiment")
        record = self.ledger.get_candidate(descriptor.candidate_id)
        if record.descriptor != descriptor:
            raise ValueError("audit descriptor differs from canonical candidate")
        stored = self.ledger.get_completions(descriptor.candidate_id)
        with self.ledger._lock:
            row = self.ledger._db.execute(
                "SELECT a.worker_id,r.attempt_number,r.reward FROM result r JOIN attempt a "
                "ON a.candidate_id=r.candidate_id AND a.attempt_number=r.attempt_number WHERE r.candidate_id=?",
                (descriptor.candidate_id,),
            ).fetchone()
        if stored is None or row is None:
            raise ValueError("audit candidate has no canonical text receipt")
        return {
            "worker_id": row[0],
            "attempt_number": row[1],
            "reward": row[2],
            "completions_sha256": stored[0],
            "completions": stored[1],
            "chunk": self.ledger.completion_chunk(descriptor.candidate_id),
        }

    def _validate_stop(self, value):
        try:
            descriptor = CandidateDescriptor.from_dict(value["descriptor"])
            original, auditor = self._original(descriptor), value["auditor"]
            texts = auditor["completions"]
            if (
                not isinstance(texts, list)
                or not texts
                or not all(isinstance(text, str) for text in texts)
                or auditor["completions_sha256"] != completions_sha256(texts)
                or auditor["completions_sha256"] == original["completions_sha256"]
                or not isinstance(auditor["worker_id"], str)
                or not auditor["worker_id"]
                or auditor["worker_id"] == original["worker_id"]
                or type(auditor["attempt_number"]) is not int
                or auditor["attempt_number"] < 1
                or auditor["chunk"] != original["chunk"]
                or set(auditor) != {"worker_id", "attempt_number", "completions_sha256", "completions", "chunk"}
                or value
                != {
                    "formatVersion": 1,
                    "experimentId": self.experiment_id,
                    "descriptor": descriptor.to_dict(),
                    "original": original,
                    "auditor": auditor,
                }
            ):
                raise ValueError("invalid receipt")
        except (KeyError, TypeError, ValueError, LedgerError) as error:
            raise ValueError("invalid or conflicting audit stop receipt") from error

    def record_audit(self, descriptor, worker, number, texts):
        """Keep first-mismatch evidence before the canonical audit write or ACK.

        A failed receipt write still stops this process. Its retry must persist the
        receipt before ACK; storage failure followed by process/power loss is not
        a durable-stop guarantee and requires separate storage-fault acceptance.
        """
        digest = completions_sha256(texts)
        with self._lock:
            if self.stop_on_mismatch:
                original = self._original(descriptor)
                if digest != original["completions_sha256"]:
                    if self._stop is None:
                        receipt = {
                            "formatVersion": 1,
                            "experimentId": self.experiment_id,
                            "descriptor": descriptor.to_dict(),
                            "original": original,
                            "auditor": {
                                "worker_id": worker,
                                "attempt_number": number,
                                "completions_sha256": digest,
                                "completions": list(texts),
                                "chunk": self.ledger.completion_chunk(descriptor.candidate_id),
                            },
                        }
                        self._validate_stop(receipt)
                        self._stop = receipt
                    if not self._stop_saved:
                        write_json(self.stop_path, self._stop)
                        self._stop_saved = True
            return self.ledger.record_audit(descriptor.candidate_id, worker, digest)
