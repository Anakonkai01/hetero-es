"""One bounded, private, atomically replaced delivery record. Never numerical replay data."""

import hashlib
import json
import os
from pathlib import Path
import tempfile


class DeliveryOutbox:
    def __init__(self, path, worker_id, scope, *, max_bytes=1 << 20):
        if not isinstance(scope, str) or not scope:
            raise ValueError("A durable outbox requires a nonempty lineage scope")
        self.path, self.worker_id, self.scope = Path(path), worker_id, scope
        self.max_bytes = max_bytes

    def _encode(self, state):
        return json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

    def load(self):
        if self.path.is_symlink():
            raise ValueError("Outbox must not be a symlink")
        try:
            with self.path.open("rb") as stream:
                data = stream.read(self.max_bytes + 1)
        except FileNotFoundError:
            return {"poisoned": False, "pending": None}
        if len(data) > self.max_bytes:
            raise ValueError("Outbox exceeds its byte limit")
        envelope = json.loads(data)
        state = envelope["state"]
        if hashlib.sha256(self._encode(state)).hexdigest() != envelope["sha256"]:
            raise ValueError("Outbox checksum mismatch")
        if state["formatVersion"] != 1 or state["workerId"] != self.worker_id or state["scope"] != self.scope:
            raise ValueError("Outbox lineage differs from this worker/run endpoint")
        if type(state["poisoned"]) is not bool:
            raise ValueError("Invalid outbox poison state")
        return state

    def save(self, pending, poisoned):
        state = {
            "formatVersion": 1,
            "workerId": self.worker_id,
            "scope": self.scope,
            "poisoned": poisoned,
            "pending": pending,
        }
        data = self._encode({"state": state, "sha256": hashlib.sha256(self._encode(state)).hexdigest()})
        if len(data) > self.max_bytes:
            raise ValueError("Outbox exceeds its byte limit")
        if self.path.is_symlink():
            raise ValueError("Outbox must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".delivery-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            # Windows does not expose directory fsync through os.open; the file itself is flushed on both OSs.
            if os.name != "nt":
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
