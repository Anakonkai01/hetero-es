"""CPU-only packaged Lab Server entry point. Bootstrap secrets arrive on stdin."""

from ..repositories.bootstrap import BootstrapRepository as repository
from ..core.server_models import Bootstrap

import ipaddress
import json
import os
from pathlib import Path
import shutil
import secrets


from .devices import AgentRuntime
from ..core.device_models import Enrollment
from ..storage.local_backend import LocalBackend
from .store import Store


def initialize(root, values):
    data = Bootstrap.model_validate(values)
    address = ipaddress.ip_address(data.host)
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise ValueError("Select a local IPv4 address")
    url = Enrollment.private_compute(f"http://{address}:{data.port}")
    storage = Path(data.storageDirectory)
    if not storage.is_absolute():
        raise ValueError("Storage directory must be absolute")
    root = Path(root)
    # A failed or interrupted previous installation is never silently overwritten.
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        backend = LocalBackend(
            storage, root / "storage-signing.key", url, data.storageVolumeUUID, root / "metadata-objects"
        )
        store = Store(root / "state/product.sqlite", {data.username: data.password}, AgentRuntime(backend))
        with store.db() as db:
            repository.server_initialize_8(db, ("dispatchHold", "true"))
        config = {
            "deploymentMode": "agent",
            "storageMode": "local",
            "serverInstanceId": secrets.token_hex(16),
            "productStateDirectory": str(root / "state"),
            "apiUrl": url,
            "serverHost": str(address),
            "serverPort": data.port,
            "storageDirectory": str(storage),
            "storageVolumeUUID": data.storageVolumeUUID,
            "metadataStorageDirectory": str(root / "metadata-objects"),
            "storageQuotaBytes": 200_000_000_000,
        }
        # The DB contains only an Argon2 password hash. There is no reusable
        # administrator password in a credentials file, process argument or log.
        for name, value in [("config.json", config), ("credentials.json", {"users": {}})]:
            with (root / name).open("x") as stream:
                os.chmod(root / name, 0o600)
                json.dump(value, stream)
        return {"initialized": True, "apiUrl": url, "dispatchHeld": True}
    except BaseException:
        shutil.rmtree(root)
        raise
