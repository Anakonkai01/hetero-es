#!/usr/bin/env python3
"""A throwaway CPU-only lab for browser/Electron checks: temporary state, fake runtime, fake installers.

    serve-test-lab.py --web <built frontend> --port 18080

Accounts: admin / test-admin-pass (platform administrator), participant / test-user-pass. It never touches the real lab,
its configuration or its installers. Stop it with Ctrl-C or SIGTERM; its state directory is deleted on exit.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend' / 'tests')]

import uvicorn  # noqa: E402
from backend.app import create_app  # noqa: E402
from test_api import Runtime  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--web', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    state = Path(tempfile.mkdtemp(prefix='test-lab-'))
    try:
        downloads = state / 'downloads'
        downloads.mkdir()
        installers = [{'platform': 'windows', 'name': 'HeteroES-Worker-test-Windows.exe', 'url': '/downloads/HeteroES-Worker-test-Windows.exe'},
                      {'platform': 'linux', 'name': 'HeteroES-Worker-test-Linux.tar.gz', 'url': '/downloads/HeteroES-Worker-test-Linux.tar.gz'}]
        for item in installers:
            (downloads / item['name']).write_bytes(b'not a real installer')
        (downloads / 'manifest.json').write_text(json.dumps({'version': '0.1.0', 'build': 'test', 'installers': installers, 'serverInstallers': []}))
        app = create_app(state / 'product.sqlite', {'admin': 'test-admin-pass', 'participant': 'test-user-pass'}, Runtime(),
                         dispatch=False, web_directory=args.web.resolve(), downloads_directory=downloads)
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        shutil.rmtree(state, ignore_errors=True)


if __name__ == '__main__':
    main()
