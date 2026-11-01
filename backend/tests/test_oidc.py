"""OIDC verification uses generated RSA keys and an actual bounded local JWKS HTTP server."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from backend.core.errors import ServiceError
from backend.services.oidc import OIDCVerifier

ISSUER = "https://identity.example.test/realms/lab"
CLIENT = "heteroes-web"


@pytest.fixture(scope="module")
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def public_jwk(key, kid):
    return {
        **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def signed(key, kid="one", **changes):
    claims = {
        "iss": ISSUER,
        "aud": CLIENT,
        "sub": "subject-1",
        "preferred_username": "researcher",
        "exp": time.time() + 300,
        **changes,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@contextmanager
def jwks_server(keys):
    state = SimpleNamespace(keys=[public_jwk(keys[0], "one")], requests=0, redirected=0, status=200, raw=None)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/sink":
                state.redirected += 1
                self.send_response(200)
                self.end_headers()
                return
            state.requests += 1
            self.send_response(state.status)
            if 300 <= state.status < 400:
                self.send_header("Location", "/sink")
            self.end_headers()
            self.wfile.write(state.raw if state.raw is not None else json.dumps({"keys": state.keys}).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    state.url = "http://127.0.0.1:" + str(server.server_port) + "/jwks"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def issuer(keys):
    with jwks_server(keys) as server:
        yield server, OIDCVerifier(ISSUER, server.url, CLIENT)


def rejected(verifier, token):
    with pytest.raises(ServiceError) as error:
        verifier.verify(token)
    assert error.value.status_code == 401
    assert token not in str(error.value)


def test_valid_signature_cached_and_authorized_party_alternative(issuer, keys):
    server, verifier = issuer
    assert verifier.verify(signed(keys[0]))["sub"] == "subject-1"
    assert verifier.verify(signed(keys[0], aud=["other", CLIENT]))["aud"] == ["other", CLIENT]
    assert verifier.verify(signed(keys[0], aud="account", azp=CLIENT))["azp"] == CLIENT
    assert server.requests == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": lambda: time.time() - 90},
        {"nbf": lambda: time.time() + 90},
        {"iss": ISSUER + "/wrong"},
        {"aud": "other"},
        {"aud": "other", "azp": "other"},
        {"sub": ""},
        {"exp": None},
        {"exp": True},
        {"exp": float("inf")},
        {"nbf": False},
        {"preferred_username": ""},
    ],
)
def test_wrong_claims_rejected(issuer, keys, changes):
    server, verifier = issuer
    rejected(
        verifier, signed(keys[0], **{name: value() if callable(value) else value for name, value in changes.items()})
    )


def test_required_expiry_and_thirty_second_leeway(issuer, keys):
    _, verifier = issuer
    assert verifier.verify(signed(keys[0], exp=time.time() - 10, nbf=time.time() + 10))["sub"] == "subject-1"
    claims = {"iss": ISSUER, "aud": CLIENT, "sub": "subject-1", "preferred_username": "r"}
    rejected(verifier, jwt.encode(claims, keys[0], algorithm="RS256", headers={"kid": "one"}))


def test_wrong_signature_and_untrusted_algorithms_never_select_a_key(issuer, keys):
    server, verifier = issuer
    rejected(verifier, jwt.encode({"sub": "forged"}, "", algorithm="none", headers={"kid": "one"}))
    rejected(
        verifier,
        jwt.encode(
            {"sub": "forged"},
            "unit-test-hmac-key-that-is-not-an-rsa-public-key",
            algorithm="HS256",
            headers={"kid": "one"},
        ),
    )
    assert server.requests == 0
    rejected(verifier, signed(keys[1]))
    rejected(verifier, "x" * 20000)
    assert server.requests == 1


def test_first_unknown_rotation_refreshes_immediately_then_misses_are_bounded(issuer, keys):
    server, verifier = issuer
    verifier.verify(signed(keys[0]))
    server.keys.append(public_jwk(keys[1], "two"))
    assert verifier.verify(signed(keys[1], kid="two"))["sub"] == "subject-1"
    assert server.requests == 2
    for number in range(100):
        rejected(verifier, signed(keys[0], kid="missing-" + str(number)))
    assert server.requests == 2
    assert verifier.verify(signed(keys[0]))["sub"] == "subject-1"


def test_expired_cache_refetches_known_key_and_fails_closed(monkeypatch, issuer, keys):
    server, verifier = issuer
    now = [10.0]
    monkeypatch.setattr("backend.services.oidc.time.monotonic", lambda: now[0])
    verifier.verify(signed(keys[0]))
    now[0] += 301
    server.keys = [public_jwk(keys[1], "one")]
    rejected(verifier, signed(keys[0]))
    assert verifier.verify(signed(keys[1]))["sub"] == "subject-1"
    now[0] += 301
    server.status = 503
    rejected(verifier, signed(keys[1]))
    for _ in range(10):
        rejected(verifier, signed(keys[1]))
    assert server.requests == 3


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_jwks_redirect_is_rejected_without_visiting_destination(issuer, keys, status):
    server, verifier = issuer
    server.status = status
    rejected(verifier, signed(keys[0]))
    assert server.requests == 1 and server.redirected == 0


@pytest.mark.parametrize("raw", [b"not-json", b"{}", b'{"keys":[]}', b"x" * 262145])
def test_invalid_or_oversized_jwks_rejected(issuer, keys, raw):
    server, verifier = issuer
    server.raw = raw
    rejected(verifier, signed(keys[0]))


def test_internal_jwks_ignores_ambient_proxy(monkeypatch, issuer, keys):
    for name in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
        monkeypatch.setenv(name, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    _, verifier = issuer
    assert verifier.verify(signed(keys[0]))["sub"] == "subject-1"


def test_encryption_duplicate_or_weak_keys_are_not_signature_keys(issuer, keys):
    server, verifier = issuer
    server.keys = [{**public_jwk(keys[0], "one"), "use": "enc"}]
    rejected(verifier, signed(keys[0]))
    server.keys = [public_jwk(keys[0], "one"), public_jwk(keys[1], "one")]
    other = OIDCVerifier(ISSUER, server.url, CLIENT)
    rejected(other, signed(keys[0]))


def test_weak_rsa_and_non_verification_keys_are_rejected(issuer, keys):
    server, verifier = issuer
    weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    server.keys = [public_jwk(weak, "one")]
    rejected(verifier, signed(weak))
    for operations in [["encrypt"], "verify", None]:
        server.keys = [{**public_jwk(keys[0], "one"), "key_ops": operations}]
        rejected(OIDCVerifier(ISSUER, server.url, CLIENT), signed(keys[0]))


def test_issuer_comparison_is_exact_and_optional_nbf_is_not_required(issuer, keys):
    _, verifier = issuer
    rejected(verifier, signed(keys[0], iss=ISSUER[:-3]))
    claims = {"iss": [ISSUER], "aud": CLIENT, "sub": "s", "preferred_username": "r", "exp": time.time() + 300}
    rejected(
        verifier, jwt.api_jws.encode(json.dumps(claims).encode(), keys[0], algorithm="RS256", headers={"kid": "one"})
    )
    assert "nbf" not in verifier.verify(signed(keys[0]))


def test_valid_but_oversized_jwks_cannot_bypass_the_read_bound(issuer, keys):
    server, verifier = issuer
    server.raw = b" " * 262145 + json.dumps({"keys": [public_jwk(keys[0], "one")]}).encode()
    rejected(verifier, signed(keys[0]))
