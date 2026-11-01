"""Slow down password guessing and registration spam. Kept in memory: a restart forgets it, which is acceptable."""

from collections import deque
import ipaddress
import threading
import time

TAILSCALE = ipaddress.ip_network("100.64.0.0/10")


class Throttle:
    """At most `limit` recorded attempts per key within `window` seconds."""

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.attempts = {}
        self.lock = threading.Lock()

    def _recent(self, key, now):
        queue = self.attempts.get(key)
        if queue is None:
            return None
        while queue and now - queue[0] >= self.window:
            queue.popleft()
        if not queue:
            del self.attempts[key]
            return None
        return queue

    def retry_after(self, key):
        """Seconds to wait before this key may try again; 0 if it may try now."""
        with self.lock:
            now = self.clock()
            queue = self._recent(key, now)
            if queue is None or len(queue) < self.limit:
                return 0
            return max(1, int(queue[0] + self.window - now + 0.999))

    def record(self, key):
        with self.lock:
            now = self.clock()
            if len(self.attempts) > 256:
                for stale in list(self.attempts):
                    self._recent(stale, now)
            queue = self._recent(key, now)
            if queue is None:
                queue = self.attempts.setdefault(key, deque())
            queue.append(now)

    def clear(self, key):
        with self.lock:
            self.attempts.pop(key, None)


def client_address(peer, headers):
    """The caller's address. Forwarding headers are believed only when the direct peer is a local proxy
    (loopback, private or Tailscale); a public peer cannot choose its own identity."""
    if not peer:
        return "unknown"
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not (address.is_loopback or address.is_private or address in TAILSCALE):
        return peer

    def header(name):
        return next((value for key, value in headers.items() if key.lower() == name), "")

    for value in (header("cf-connecting-ip"), header("x-forwarded-for").split(",")[0]):
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError:
            continue
    return peer
