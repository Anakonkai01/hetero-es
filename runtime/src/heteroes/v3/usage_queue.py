"""Bounded best-effort metrics delivery. Canonical results never wait for a slow usage store."""

from collections import deque
import json
import math
import threading

from heteroes.v3.usage import validate_usage


class BoundedUsageSink:
    def __init__(self, sink, *, capacity=64, max_record_bytes=65536):
        if type(capacity) is not int or capacity < 1 or type(max_record_bytes) is not int or max_record_bytes < 1:
            raise ValueError("Usage queue bounds must be positive integers")
        self._sink, self._capacity, self._max_bytes = sink, capacity, max_record_bytes
        self._condition = threading.Condition()
        self._entries, self._ready = {}, deque()
        self._closed, self._thread = False, None
        self._errors = self._dropped = 0

    def __call__(self, descriptor, attempt, worker, usage, kind):
        key = (descriptor.candidate_id, attempt, worker, kind)
        if isinstance(usage, dict) and isinstance(usage.get("generatedTokens"), list):
            if len(usage["generatedTokens"]) > self._max_bytes:
                with self._condition:
                    self._dropped += 1
                return False
        value = validate_usage(usage)
        body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        size = len(body.encode()) + len(str(key).encode())
        with self._condition:
            if self._closed or size > self._max_bytes:
                self._dropped += 1
                return False
            if key in self._entries:
                if self._entries[key][0] != body:
                    self._errors += 1
                    return False
                return True
            # The active sink call stays in entries: capacity bounds queued AND in-flight payloads.
            if len(self._entries) >= self._capacity:
                self._dropped += 1
                return False
            self._entries[key] = (body, (descriptor, attempt, worker, value, kind))
            self._ready.append(key)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="heteroes-usage", daemon=True)
                self._thread.start()
            self._condition.notify_all()
        return True

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._ready or self._closed)
                if not self._ready:
                    return
                key = self._ready.popleft()
                args = self._entries[key][1]
            try:
                self._sink(*args)
            except Exception:
                with self._condition:
                    self._errors += 1
            finally:
                with self._condition:
                    self._entries.pop(key)
                    self._condition.notify_all()

    def flush(self, timeout):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Usage flush timeout must be finite and nonnegative")
        with self._condition:
            return self._condition.wait_for(lambda: not self._entries, timeout)

    def close(self, timeout=0):
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        return self.flush(timeout)

    def status(self):
        with self._condition:
            return {
                "pending": len(self._entries),
                "errors": self._errors,
                "dropped": self._dropped,
                "partial": bool(self._entries or self._errors or self._dropped),
            }
