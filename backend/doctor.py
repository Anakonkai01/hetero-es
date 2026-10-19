"""Read-only preflight for a Local Lab Server. It changes no lab file (SQLite may create its
-shm coordination file when it opens the WAL database); exit status 1 if any check FAILs.

    python -m backend.doctor --private ~/.config/heteroes-m2
"""
from .policies import dispatch_held
from .config import load_config
import argparse
from pathlib import Path
import shutil
import sqlite3
import sys
import time

from .addresses import endpoint, is_private
from .migrations import SCHEMA_VERSION

PASS, WARN, FAIL = 'PASS', 'WARN', 'FAIL'
LOW_FREE_BYTES = 10 * 10**9


def run_checks(private):
    """Return [(level, name, message)]. The directory is only ever read."""
    private = Path(private)
    out = []

    def add(level, name, message):
        out.append((level, name, message))

    try:
        config = load_config(private)
    except (OSError, ValueError):
        add(FAIL, 'configuration', f'{private}/config.json is missing or is not valid JSON')
        return out
    add(PASS, 'configuration', 'config.json is readable')

    if config.get('deploymentMode') == 'agent':
        add(PASS, 'mode', 'agent mode (the only supported control mode)')
    else:
        add(FAIL, 'mode', 'deploymentMode is not "agent"; the older control mode is not supported')

    api = config.get('apiUrl', '')
    try:
        endpoint(api, private=True)
    except ValueError:
        add(FAIL, 'address', f'apiUrl "{api}" must be a numeric private, loopback or Tailscale address; names and public addresses are not accepted')
    else:
        host = api.split('//', 1)[-1].split(':')[0]
        if host.startswith('127.'):
            add(WARN, 'address', 'apiUrl is a loopback address: only this computer can reach the lab')
        else:
            add(PASS, 'address', f'apiUrl {api} is a private address; keep it fixed (DHCP reservation) or the lab breaks when it changes')
        if api.startswith('https://'):
            add(PASS, 'transport', 'traffic to the Lab Server is encrypted')
        else:
            add(WARN, 'transport', 'plain HTTP: session and device tokens are not encrypted. Fine on a trusted LAN; use an encrypted overlay (WireGuard, Tailscale) on a shared network')

    public = [config.get(k) for k in ('publicWebUrl', 'publicComputeUrl') if config.get(k)]
    if public:
        bad = []
        for url in public:
            try:
                endpoint(url)
                if is_private(url):
                    bad.append(url)
            except ValueError:
                bad.append(url)
        if bad:
            add(FAIL, 'public', 'public address must be an HTTPS host name: ' + ', '.join(bad))
        elif any('trycloudflare.com' in url for url in public):
            add(WARN, 'public', 'the public address is a temporary Quick Tunnel: it changes whenever the tunnel restarts')
        else:
            add(PASS, 'public', 'public addresses are HTTPS host names')
        add(PASS, 'installers', 'installers are served on the public address' if config.get('publicDownloads')
            else 'installers are private: they download only over the LAN or Tailscale address')

    database = private / 'state' / 'product.sqlite'
    held, online = None, None
    try:
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise sqlite3.DatabaseError('integrity check failed')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION:
                add(FAIL, 'database', f'database schema {version} is newer than this program knows ({SCHEMA_VERSION}); use the newer release')
            else:
                add(PASS, 'database', f'product.sqlite is intact (schema {version})')
            held = dispatch_held(db)
            reservations = db.execute('SELECT count(*) FROM physical_reservations').fetchone()[0] if db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='physical_reservations'").fetchone() else 0
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='devices'").fetchone():
                rows = db.execute('SELECT status, seen FROM devices').fetchall()
                online = sum(1 for status, seen in rows if status == 'APPROVED' and time.time() - seen < 30)
                add(PASS if online else WARN, 'devices',
                    f'{len(rows)} device(s) enrolled, {online} approved and online' + ('' if online else ': no GPU is available right now'))
    except (sqlite3.Error, OSError, ValueError, TypeError):
        add(FAIL, 'database', f'{database} is missing, damaged or unreadable')
    else:
        add(WARN if held else PASS, 'dispatch',
            'the queue is held: new experiments will not start until an administrator resumes it in Operations' if held
            else 'the queue is open')
        if reservations:
            add(WARN, 'reservations', f'{reservations} physical GPU reservation(s) are active')

    storage = config.get('storageDirectory')
    if not storage:
        add(WARN, 'storage', 'no storageDirectory configured: recovery points cannot be kept')
    elif not Path(storage).is_dir():
        add(FAIL, 'storage', f'storage directory {storage} does not exist (is the disk mounted?)')
    else:
        free = shutil.disk_usage(storage).free
        if free < LOW_FREE_BYTES:
            add(WARN, 'storage', f'only {free / 1e9:.1f} GB free in {storage}; a model checkpoint is about 1 GB')
        else:
            add(PASS, 'storage', f'{free / 1e9:.0f} GB free in {storage}')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--private', type=Path, required=True, help='private lab directory (contains config.json)')
    results = run_checks(parser.parse_args(argv).private)
    for level, name, message in results:
        print(f'{level:4}  {name:14} {message}')
    failed = sum(level == FAIL for level, _, _ in results)
    print('\n' + (f'{failed} check(s) FAILED.' if failed else 'No failures.'))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
