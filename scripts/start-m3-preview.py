#!/usr/bin/env python3
"""Restart only the held local M3 CPU API and web preview after a host reboot."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import time

REPO = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / '.config/heteroes-m2'
HOST = '100.110.165.40'


def birth(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except FileNotFoundError:
        return None


def listening(port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex((HOST, port)) == 0


def main():
    config = json.loads((PRIVATE / 'config.json').read_text())
    if config.get('deploymentMode') != 'agent':
        raise RuntimeError('The preview requires the existing local agent-mode configuration')
    database = Path(config['productStateDirectory']) / 'product.sqlite'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        held = db.execute('SELECT value FROM settings WHERE key="dispatchHold"').fetchone()
        if not held or json.loads(held[0]) is not True:
            raise RuntimeError('Hold dispatch in Operations before restarting this review preview')
    python = REPO.parent / 'Hetero-ES-LLM/.venv-backend/bin/python'
    if not python.is_file():
        raise RuntimeError('The existing local backend environment is required')
    environment = dict(os.environ, HETEROES_PRIVATE_CONFIG=str(PRIVATE),
        HETEROES_UI_URL=f'http://{HOST}:5181', HETEROES_UI_HOST=HOST,
        HETEROES_UI_PORT='5181', HETEROES_BACKEND_HOST=HOST,
        HETEROES_BACKEND_PORT='8002', VITE_DATA_SOURCE='real', CUDA_VISIBLE_DEVICES='')
    services = [
        ('backend', 8002, [str(python), '-m', 'uvicorn', 'backend.app:app_from_environment',
            '--factory', '--host', HOST, '--port', '8002']),
        ('web', 5181, ['npm', 'run', 'dev', '--workspace', 'frontend']),
    ]
    for name, port, command in services:
        record_path = PRIVATE / f'{name}-m3-process.json'
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        if record.get('birth') and birth(record['pid']) == record['birth']:
            if not listening(port):
                raise RuntimeError(f'Tracked {name} is alive but its port is unavailable')
            continue
        if listening(port):
            raise RuntimeError(f'Port {port} belongs to an untracked process; nothing was stopped')
        log_path = PRIVATE / f'{name}-m3.log'
        with log_path.open('ab') as output:
            os.chmod(log_path, 0o600)
            process = subprocess.Popen(command, cwd=REPO, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
        record_path.write_text(json.dumps({'pid': process.pid, 'birth': birth(process.pid),
            'sourceDirectory': str(REPO), 'uiUrl': f'http://{HOST}:5181'}))
        os.chmod(record_path, 0o600)
        deadline = time.monotonic() + 30
        while not listening(port):
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f'{name} did not start; inspect its private log')
            time.sleep(.2)
    print(f'M3 preview: http://{HOST}:5181 (dispatch held; no compute agent started)')


if __name__ == '__main__':
    main()
