from .policies import dispatch_held
"""CPU deployment validation and public entrypoint configuration. No GPU imports."""
import json
import os
from pathlib import Path
import sqlite3
from .addresses import endpoint


def save_private(path, value):
    path=Path(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(value,out,indent=2)
        out.flush();os.fsync(out.fileno())
    os.replace(temporary,path)


def idle(config):
    path=Path(config['productStateDirectory'])/'product.sqlite'
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        if dispatch_held(db) is not True:
            raise RuntimeError('Hold dispatch before deployment maintenance')
        for table in ('device_reservations','physical_reservations'):
            if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:
                raise RuntimeError('Confirm all assignments drained before deployment maintenance')


def caddyfile(config):
    api=endpoint(config['apiUrl'],private=True)
    compute=endpoint(config['privateComputeUrl'],private=True)
    ports=[config.get('webEntryPort',8080),config.get('computeEntryPort',8081)]
    if any(type(p) is not int or not 1024<=p<=65535 for p in ports) or len(set(ports))!=2:
        raise ValueError('Select distinct unprivileged entry ports')
    public_downloads=config.get('publicDownloads',False)
    if type(public_downloads) is not bool:
        raise ValueError('publicDownloads must be true or false')
    # Installers are the only bulk path an operator may open to the public entry;
    # model weights, storage capabilities and backups always need a private route.
    bulk=('/downloads/* ' if not public_downloads else '')+'/api/v1/datasets/import /api/v1/local-storage/* /api/v1/cloud-downloads/* /api/v1/artifacts/*/download-ticket /api/v1/platform/backups/*/download /api/v1/platform/backups/*/download-ticket'
    # Caddy's admin endpoint is disabled. Separate loopback listeners prevent
    # a forged Host header from selecting the private bulk entrypoint.
    return '''{
    admin off
    auto_https off
}
http://:%d {
    bind 127.0.0.1
    request_body {
        max_size 3MB
    }
    header X-Content-Type-Options nosniff
    header Referrer-Policy no-referrer
    @manifest path /downloads/manifest.json
    handle @manifest {
        reverse_proxy %s
    }
    @bulk path %s
    handle @bulk {
        respond "Private LAN/Tailscale transfer required" 403
    }
    handle {
        # Server-sent events (the live run view) must reach the browser as they are produced.
        reverse_proxy %s {
            flush_interval -1
        }
    }
}
http://:%d {
    bind 127.0.0.1
    request_body {
        max_size 1MB
    }
    @control path /v1/health /v1/job /v1/leases /v1/heartbeats /v1/results /v1/failures /v1/updates/*
    handle @control {
        reverse_proxy %s
    }
    handle {
        respond "Private LAN/Tailscale transfer required" 403
    }
}
''' % (ports[0],api,bulk,api,ports[1],compute)
