"""CPU-only packaged Lab Server entry point. Bootstrap secrets arrive on stdin."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import shutil
import secrets
import signal
import sys
import threading

from pydantic import BaseModel, ConfigDict, Field

from .devices import AgentRuntime, Enrollment
from .local_storage import LocalBackend
from .store import Store


class Bootstrap(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=2, max_length=100, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=200)
    host: str
    port: int = Field(ge=1024, le=65535, strict=True)
    storageDirectory: str
    storageVolumeUUID: str | None = None


def initialize(root, values):
    data = Bootstrap.model_validate(values)
    address = ipaddress.ip_address(data.host)
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise ValueError('Select a local IPv4 address')
    url = Enrollment.private_compute(f'http://{address}:{data.port}')
    storage = Path(data.storageDirectory)
    if not storage.is_absolute():
        raise ValueError('Storage directory must be absolute')
    root = Path(root)
    # A failed or interrupted previous installation is never silently overwritten.
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        backend = LocalBackend(storage, root/'storage-signing.key', url, data.storageVolumeUUID)
        store = Store(root/'state/product.sqlite', {data.username:data.password}, AgentRuntime(backend))
        with store.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('dispatchHold','true'))
        config = {'deploymentMode':'agent', 'storageMode':'local',
                  'serverInstanceId':secrets.token_hex(16),
                  'productStateDirectory':str(root/'state'), 'apiUrl':url,
                  'serverHost':str(address), 'serverPort':data.port,
                  'storageDirectory':str(storage), 'storageVolumeUUID':data.storageVolumeUUID,
                  'storageQuotaBytes':200_000_000_000}
        # The DB contains only an Argon2 password hash. There is no reusable
        # administrator password in a credentials file, process argument or log.
        for name, value in [('config.json',config), ('credentials.json',{'users':{}})]:
            with (root/name).open('x') as stream:
                os.chmod(root/name,0o600); json.dump(value,stream)
        return {'initialized':True, 'apiUrl':url, 'dispatchHeld':True}
    except BaseException:
        shutil.rmtree(root)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private', type=Path, required=True)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--web', type=Path)
    parser.add_argument('--downloads',type=Path)
    args = parser.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    if args.initialize:
        try:
            result = initialize(args.private, json.loads(sys.stdin.buffer.read(16385)))
        except Exception:
            # Pydantic errors can include input secrets; do not print them.
            print(json.dumps({'error':'SERVER_INITIALIZATION_FAILED'})); return 1
        print(json.dumps(result)); return 0
    if args.web is None:
        parser.error('--web is required for serving')
    config = json.loads((args.private/'config.json').read_text())
    os.environ['HETEROES_PRIVATE_CONFIG'] = str(args.private)
    os.environ['HETEROES_WEB_DIRECTORY'] = str(args.web)
    if args.downloads:
        os.environ['HETEROES_DOWNLOADS_DIRECTORY']=str(args.downloads)
    os.environ['HETEROES_UI_URL'] = config['apiUrl']

    def parent_pipe():
        # The desktop owns this process. Closing its pipe on exit/crash stops
        # only this API; outbound workers retain durable outage evidence.
        sys.stdin.buffer.read(1)
        os.kill(os.getpid(), signal.SIGTERM)

    import uvicorn
    threading.Thread(target=parent_pipe,daemon=True).start()
    uvicorn.run('backend.app:app_from_environment',factory=True,
                host=config['serverHost'],port=config['serverPort'],access_log=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
