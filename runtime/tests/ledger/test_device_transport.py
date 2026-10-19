"""A run credential is identity, not merely permission to reach the server."""

from test_http import clock, ledger, api, post, raw
from heteroes.http_transport import CoordinatorServer


def test_device_cannot_claim_another_alias_or_submit_its_attempt(api):
    server = CoordinatorServer(
        api, token="legacy-disabled", device_tokens={"alice": "alice-secret", "bob": "bob-secret"}
    )
    server.start()
    try:
        alice = {"Authorization": "Bearer alice-secret"}
        bob = {"Authorization": "Bearer bob-secret"}
        assert raw(server, "GET", "/v1/job", headers={"Authorization": "Bearer legacy-disabled"})[0] == 401
        assert post(server, "/v1/leases", {"worker_id": "bob"}, alice)[0] == 403
        status, _, reply = post(server, "/v1/leases", {"worker_id": "alice"}, alice)
        assert status == 200
        work = reply["work"]
        body = {k: work[k] for k in ("descriptor", "attempt_number", "token")}
        assert post(server, "/v1/results", {**body, "reward": 1}, bob)[0] == 403
        assert post(server, "/v1/heartbeats", body, bob)[0] == 403
        assert post(server, "/v1/failures", {**body, "kind": "OTHER"}, bob)[0] == 403
        assert post(server, "/v1/results", {**body, "reward": 1}, alice)[0] == 200
        assert post(server, "/v1/results", {**body, "reward": 1}, alice)[0] == 200
    finally:
        server.stop()
