"""Server-sent events for one run: the compact timeline is pushed when it changes, with heartbeats in between."""
import asyncio
import json
import threading

from starlette.concurrency import run_in_threadpool

from .store import TERMINAL
from .timeline import build_timeline


class LiveStreams:
    """Limits how many viewers may hold a stream open and carries the pacing settings."""

    def __init__(self, limit=25, poll=0.7, heartbeat=15.0, max_seconds=3600.0):
        self.limit, self.poll, self.heartbeat, self.max_seconds = limit, poll, heartbeat, max_seconds
        self.active = 0
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            if self.active >= self.limit:
                return False
            self.active += 1
            return True

    def release(self):
        with self._lock:
            self.active = max(0, self.active - 1)

    async def frames(self, store, run_id):
        """Yield SSE text. The caller must have acquired a slot; it is released when the stream ends for any reason."""
        loop = asyncio.get_running_loop()
        started, last_sent, quiet, fingerprint = loop.time(), loop.time(), 0.0, None
        try:
            while True:
                body, snapshot = await run_in_threadpool(lambda: (store.get(run_id), store.snapshot(run_id)))
                # The clock is left out of the comparison: only real changes are worth sending.
                current = json.dumps(build_timeline(body, snapshot, now_ms=0), sort_keys=True, separators=(',', ':'), allow_nan=False)
                if current != fingerprint:
                    fingerprint = current
                    payload = json.dumps(build_timeline(body, snapshot), separators=(',', ':'), allow_nan=False)
                    yield f'event: timeline\ndata: {payload}\n\n'
                    last_sent = loop.time()
                if not body or body.get('status') in TERMINAL or loop.time() - started > self.max_seconds:
                    yield 'event: end\ndata: {}\n\n'
                    return
                await asyncio.sleep(self.poll)
                quiet = loop.time() - last_sent
                if quiet >= self.heartbeat:
                    yield ': heartbeat\n\n'
                    last_sent = loop.time()
        finally:
            self.release()
