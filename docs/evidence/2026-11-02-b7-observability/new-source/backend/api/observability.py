"""ASGI request observations never inspect query strings, headers, bodies or exception messages."""

import json
import time
import uuid

from ..services.observability import emit_request

_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"})


class RequestObservability:
    def __init__(self, app, *, metrics, service):
        self.app, self.metrics, self.service = app, metrics, service

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id, started, status, failed, finished = uuid.uuid4().hex, False, 500, False, False
        begin = time.perf_counter()
        raw_method = scope.get("method")
        method = raw_method if raw_method in _METHODS else "OTHER"

        async def observed_send(message):
            nonlocal started, status, finished
            if message["type"] == "http.response.start":
                started, status = True, message["status"]
                message = {**message, "headers": [*message.get("headers", []), (b"x-request-id", request_id.encode())]}
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finished = True
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        except Exception:
            failed = True
            # Avoid a second server exception traceback containing credential-bearing messages. The wire response is safe.
            if not started:
                await observed_send(
                    {"type": "http.response.start", "status": 500, "headers": [(b"content-type", b"application/json")]}
                )
                await observed_send(
                    {"type": "http.response.body", "body": json.dumps({"message": "Internal server error"}).encode()}
                )
            elif not finished:
                await observed_send({"type": "http.response.body", "body": b""})
        except BaseException:
            failed = True
            raise
        finally:
            route = getattr(scope.get("route"), "path", None)
            route = route if isinstance(route, str) and len(route) <= 256 else "_unmatched"
            duration = max(0.0, time.perf_counter() - begin)
            self.metrics.observe(method, route, status, duration)
            emit_request(self.service, method, route, status, duration, request_id, failed=failed)
