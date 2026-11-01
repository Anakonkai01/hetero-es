"CPU-only packaged Lab Server entry point. Bootstrap secrets arrive on stdin."

import argparse
from pathlib import Path
import sys
import json
import os
import signal
import threading
from ..core.config import load_config
from ..services.bootstrap import initialize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--web", type=Path)
    parser.add_argument("--downloads", type=Path)
    parser.add_argument("--headless", action="store_true", help="Run without a desktop parent pipe")
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    if args.initialize:
        try:
            result = initialize(args.private, json.loads(sys.stdin.buffer.read(16385)))
        except Exception:
            # Pydantic errors can include input secrets; do not print them.
            print(json.dumps({"error": "SERVER_INITIALIZATION_FAILED"}))
            return 1
        print(json.dumps(result))
        return 0
    if args.web is None:
        parser.error("--web is required for serving")
    config = load_config(args.private)
    os.environ["HETEROES_PRIVATE_CONFIG"] = str(args.private)
    os.environ["HETEROES_WEB_DIRECTORY"] = str(args.web)
    if args.downloads:
        os.environ["HETEROES_DOWNLOADS_DIRECTORY"] = str(args.downloads)
    os.environ["HETEROES_UI_URL"] = config.get("publicWebUrl") or config["apiUrl"]

    def parent_pipe():
        # The desktop owns this process. Closing its pipe on exit/crash stops
        # only this API; outbound workers retain durable outage evidence.
        sys.stdin.buffer.read(1)
        os.kill(os.getpid(), signal.SIGTERM)

    import uvicorn

    if not args.headless:
        threading.Thread(target=parent_pipe, daemon=True).start()
    from urllib.parse import urlsplit

    address = urlsplit(config["apiUrl"])
    uvicorn.run(
        "backend.apps.factory:app_from_environment",
        factory=True,
        host=config.get("serverHost", address.hostname),
        port=config.get("serverPort", address.port or 80),
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
