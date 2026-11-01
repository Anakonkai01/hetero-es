"""RS256 identity verification with bounded, no-redirect internal JWKS retrieval. Cloud dependencies load lazily."""

from collections import OrderedDict
import json
import math
import threading
import time
from urllib.parse import urlsplit

from ..core.errors import ServiceError
from ..repositories.accounts import AccountsRepository, AccountExists

_MAX_JWKS = 262144


class OIDCVerifier:
    def __init__(self, issuer, jwks_url, client_id="heteroes-web"):
        for value in (issuer, jwks_url):
            try:
                url = urlsplit(value)
                valid = (
                    url.scheme in {"http", "https"}
                    and url.hostname
                    and not (url.username or url.password or url.query or url.fragment)
                )
                url.port
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError("OIDC requires explicit issuer and JWKS HTTP URLs without credentials or queries")
        if not isinstance(client_id, str) or not client_id:
            raise ValueError("OIDC requires a client ID")
        self.issuer, self.jwks_url, self.client_id = issuer, jwks_url, client_id
        self._keys, self._negative = {}, OrderedDict()
        self._expires = 0
        self._last_fetch = self._last_unknown = float("-inf")
        self._lock = threading.RLock()

    def _refresh(self, now):
        import jwt
        from heteroes.http_safety import opener

        self._last_fetch = now
        with opener(proxy=False).open(self.jwks_url, timeout=5) as response:
            if response.status != 200:
                raise ValueError("Invalid JWKS response")
            payload = response.read(_MAX_JWKS + 1)
        if len(payload) > _MAX_JWKS:
            raise ValueError("JWKS too large")
        values = json.loads(payload).get("keys")
        if not isinstance(values, list) or not 1 <= len(values) <= 32:
            raise ValueError("Invalid JWKS keys")
        keys = {}
        for value in values:
            if not isinstance(value, dict):
                raise ValueError("Invalid JWKS key")
            if value.get("kty") != "RSA" or value.get("use", "sig") != "sig" or value.get("alg", "RS256") != "RS256":
                continue
            if "key_ops" in value:
                operations = value["key_ops"]
                if not isinstance(operations, list) or "verify" not in operations:
                    continue
            kid = value.get("kid")
            if not isinstance(kid, str) or not 1 <= len(kid) <= 128 or kid in keys:
                raise ValueError("Invalid JWKS key ID")
            key = jwt.PyJWK.from_dict(value, algorithm="RS256").key
            if key.key_size < 2048:
                raise ValueError("Weak RSA key")
            keys[kid] = key
        if not keys:
            raise ValueError("No signature keys")
        self._keys, self._expires = keys, now + 300
        self._negative.clear()

    def _key(self, kid):
        with self._lock:
            now = time.monotonic()
            refreshed = False
            if now >= self._expires:
                if now - self._last_fetch < 5:
                    raise ValueError("JWKS retry is bounded")
                self._refresh(now)
                refreshed = True
            if kid in self._keys:
                return self._keys[kid]
            if self._negative.get(kid, 0) > now:
                raise ValueError("Unknown key")
            # The first rotation refreshes even immediately after a successful known-key lookup. Further unknown
            # IDs cannot generate an unbounded network request stream; the negative cache itself is bounded too.
            if not refreshed and now - self._last_unknown >= 5:
                self._last_unknown = now
                self._refresh(now)
                if kid in self._keys:
                    return self._keys[kid]
            self._negative[kid] = now + 30
            if len(self._negative) > 64:
                self._negative.popitem(last=False)
            raise ValueError("Unknown key")

    def verify(self, token):
        import jwt

        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise ValueError("Invalid token size")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise ValueError("Invalid signature header")
            claims = jwt.decode(
                token,
                self._key(kid),
                algorithms=["RS256"],
                issuer=self.issuer,
                leeway=30,
                options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
            for name in ("exp", "nbf"):
                if name in claims and (type(claims[name]) not in {int, float} or not math.isfinite(claims[name])):
                    raise ValueError("Invalid time claim")
            audience = claims.get("aud", [])
            if isinstance(audience, str):
                audience = [audience]
            if not isinstance(audience, list) or any(not isinstance(value, str) for value in audience):
                raise ValueError("Invalid audience")
            if self.client_id not in audience and claims.get("azp") != self.client_id:
                raise ValueError("Wrong audience")
            for name, limit in (("sub", 255), ("preferred_username", 128)):
                value = claims.get(name)
                if not isinstance(value, str) or not value.strip() or len(value) > limit:
                    raise ValueError("Invalid identity")
            return claims
        except Exception:
            # Library/network exceptions may embed the raw JWT, URLs or untrusted JWKS payload. Keep them private.
            raise ServiceError(401, "Identity token expired or could not be verified") from None


class OIDCAccounts:
    mode = "oidc"

    def __init__(self, store, verifier):
        self.store, self.verifier = store, verifier
        self.repository = AccountsRepository()

    def current(self, token):
        claims = self.verifier.verify(token)
        identifier = "kc:" + claims["sub"]
        realm = claims.get("realm_access")
        roles = realm.get("roles", []) if isinstance(realm, dict) else []
        administrator = isinstance(roles, list) and "lab-admin" in roles
        with self.store.db() as db:
            row = self.repository.profile(db, identifier)
            collision = self.repository.by_username(db, claims["preferred_username"])
            if collision and collision["id"] != identifier:
                raise ServiceError(409, "Identity username is already assigned; contact the lab administrator")
            if row:
                profile = json.loads(row[0])
                # Realm roles never revive a suspended/rejected account or overwrite durable approval decisions.
                profile.update(
                    username=claims["preferred_username"],
                    platformAdmin=administrator and profile["accountStatus"] == "ACTIVE",
                )
                self.repository.save_profile(db, identifier, json.dumps(profile))
            else:
                profile = {
                    "userId": identifier,
                    "username": claims["preferred_username"],
                    "displayName": claims["preferred_username"],
                    "accountStatus": "ACTIVE" if administrator else "PENDING",
                    "platformAdmin": administrator,
                    "canCreateWorkspace": administrator,
                }
                try:
                    self.repository.add_user(db, identifier, "!oidc", json.dumps(profile))
                except AccountExists:
                    raise ServiceError(
                        409, "Identity username is already assigned; contact the lab administrator"
                    ) from None
                if administrator:
                    self.repository.bootstrap_membership(db, identifier)
                self.store.audit(db, identifier, "OIDC_REGISTER", identifier)
        return profile

    def download_session(self, token, user_id):
        import hashlib

        claims = self.verifier.verify(token)
        if "kc:" + claims["sub"] != user_id or claims["exp"] <= time.time():
            raise ServiceError(401, "Identity token expired")
        return "oidc:" + hashlib.sha256(token.encode()).hexdigest(), min(time.time() + 60, claims["exp"])

    @staticmethod
    def external_download_session(digest):
        import re

        return bool(re.fullmatch(r"oidc:[a-f0-9]{64}", digest))

    def sign_out(self, token):
        import hashlib

        with self.store.db() as db:
            self.repository.delete_download_tickets(db, "oidc:" + hashlib.sha256(token.encode()).hexdigest())
