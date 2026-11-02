"""Read private configuration and explicit container overrides on demand, without logging secrets."""

from copy import deepcopy
import json
import os
from pathlib import Path

_FIELDS = {
    "HETEROES_AUTH_MODE": "authMode",
    "HETEROES_OIDC_ISSUER": "oidcIssuer",
    "HETEROES_OIDC_JWKS_URL": "oidcJwksUrl",
    "HETEROES_PUBLIC_URL": "publicWebUrl",
    "HETEROES_PUBLIC_COMPUTE_URL": "publicComputeUrl",
    "HETEROES_BULK_API_URL": "bulkApiUrl",
    "HETEROES_STORAGE_MODE": "storageMode",
    "HETEROES_STORAGE_DIRECTORY": "storageDirectory",
    "HETEROES_STORAGE_METADATA_DIRECTORY": "metadataStorageDirectory",
    "HETEROES_STORAGE_SIGNING_KEY_FILE": "storageSigningKeyFile",
}
_S3_FIELDS = {
    "HETEROES_STORAGE_INTERNAL_ENDPOINT": "endpointUrl",
    "HETEROES_STORAGE_DEVICE_ENDPOINT": "deviceEndpointUrl",
    "HETEROES_STORAGE_REGION": "region",
    "HETEROES_STORAGE_STAGING_DIRECTORY": "stagingDirectory",
    "HETEROES_STORAGE_SIGNING_KEY_FILE": "signingKeyFile",
}
_SECRETS = {
    "HETEROES_DATABASE_URL": "databaseUrl",
    "HETEROES_STORAGE_ACCESS_KEY_ID": "accessKeyId",
    "HETEROES_STORAGE_SECRET_ACCESS_KEY": "secretAccessKey",
}
_BUCKETS = {
    "HETEROES_STORAGE_" + purpose.upper() + "_BUCKET": purpose for purpose in ("recovery", "datasets", "backups")
}
_ENVIRONMENT = (
    set(_FIELDS)
    | set(_S3_FIELDS)
    | set(_BUCKETS)
    | set(_SECRETS)
    | {name + "_FILE" for name in _SECRETS}
    | {"HETEROES_STATE_DIRECTORY", "HETEROES_STORAGE_QUOTA_BYTES", "HETEROES_SERVICE", "HETEROES_CREDENTIALS_FILE"}
)


def _secret(environ, name):
    direct, source = environ.get(name), environ.get(name + "_FILE")
    if direct is not None and source is not None:
        raise ValueError("Configure only one of " + name + " and its secret file")
    if source is not None:
        try:
            with Path(source).open() as stream:
                direct = stream.read(65537)
        except (OSError, ValueError):
            raise ValueError("Cannot read secret file for " + name) from None
    if direct is not None:
        if not direct or len(direct) > 65536 or not direct.rstrip("\r\n"):
            raise ValueError("Invalid secret value for " + name)
        return direct.rstrip("\r\n")
    return None


def _overlay(original, root, environ):
    config = deepcopy(original)
    state = (
        Path(
            environ.get("HETEROES_STATE_DIRECTORY")
            or config.get("productStateDirectory")
            or (Path(root) / "state" if root else Path.home() / ".local/share/heteroes-cloud")
        )
        .expanduser()
        .resolve()
    )
    if not config:
        config = {
            "deploymentMode": "agent",
            "productStateDirectory": str(state),
            "apiUrl": "http://127.0.0.1:8000",
            "storageMode": "local",
            "storageDirectory": str(state / "objects"),
            "metadataStorageDirectory": str(state / "metadata"),
        }
    if "HETEROES_STATE_DIRECTORY" in environ:
        config["productStateDirectory"] = str(state)
    for name, key in _FIELDS.items():
        if name in environ:
            config[key] = environ[name]
    for name, allowed in (("HETEROES_AUTH_MODE", {"local", "oidc"}), ("HETEROES_STORAGE_MODE", {"local", "s3"})):
        if name in environ and environ[name] not in allowed:
            raise ValueError("Invalid " + name)
    quota = None
    if "HETEROES_STORAGE_QUOTA_BYTES" in environ:
        try:
            quota = int(environ["HETEROES_STORAGE_QUOTA_BYTES"])
            if not 0 < quota <= 2**63 - 1:
                raise ValueError
        except ValueError:
            raise ValueError("Invalid HETEROES_STORAGE_QUOTA_BYTES") from None
        config["storageQuotaBytes"] = quota
    s3 = config.get("s3", {})
    if not isinstance(s3, dict):
        raise ValueError("Invalid S3 configuration object")
    for name, key in _S3_FIELDS.items():
        if name in environ:
            s3[key] = environ[name]
    for name, key in _SECRETS.items():
        value = _secret(environ, name)
        if value is not None:
            (config if key == "databaseUrl" else s3)[key] = value
    if config.get("storageMode") == "s3":
        s3.setdefault("stagingDirectory", str(state / "s3-staging"))
        s3.setdefault("signingKeyFile", str(state / "storage-signing.key"))
        s3.setdefault("region", "us-east-1")
        buckets = s3.setdefault("buckets", {purpose: "heteroes-" + purpose for purpose in _BUCKETS.values()})
        if not isinstance(buckets, dict):
            raise ValueError("Invalid S3 bucket configuration")
        for name, purpose in _BUCKETS.items():
            if name in environ:
                buckets[purpose] = environ[name]
        if quota is not None:
            s3["quotaBytes"] = quota
    if s3:
        config["s3"] = s3
    return config


def load_config(root=None, *, optional=False):
    root = root or os.environ.get("HETEROES_PRIVATE_CONFIG")
    overrides = any(name in os.environ for name in _ENVIRONMENT)
    config = {}
    if root:
        try:
            config = json.loads((Path(root) / "config.json").read_text())
            if not isinstance(config, dict):
                raise ValueError
        except FileNotFoundError:
            if not (optional or overrides):
                raise
        except (OSError, ValueError):
            if not optional:
                raise ValueError("Private configuration must be a readable JSON object") from None
            config = {}
    elif not (optional or overrides):
        raise ValueError("Set HETEROES_PRIVATE_CONFIG or explicit container settings")
    return _overlay(config, root, os.environ) if overrides else config
