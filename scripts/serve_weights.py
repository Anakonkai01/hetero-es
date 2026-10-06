#!/usr/bin/env python3
"""
Serve the pinned model's weights over HTTP and nothing else, so that a worker can measure the link and the synchronization
(`scripts/profile_worker.py --sync-url ...`) before any experiment is running.

    python scripts/serve_weights.py --model-path <snapshot dir> --weights-dir ~/.cache/heteroes/published --host 10.10.10.1 --port 8766

It prints one JSON line with the URL and the SHA-256 of the weights (the name of the file the worker will ask for), then waits
until it is stopped (SIGINT or SIGTERM).
"""
import argparse
import json
import signal
import sys
import threading
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--weights-dir", default=str(Path.home() / ".cache" / "heteroes" / "published"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)

    from heteroes.http_transport import CoordinatorServer
    from heteroes.model.loading import load_pinned_model
    from heteroes.model.weights_io import publish_weights

    loaded = load_pinned_model(args.model_path, "cpu")
    sha256 = publish_weights(loaded.model, loaded.schema, args.weights_dir)
    server = CoordinatorServer(None, job=None, models_dir=args.weights_dir, host=args.host, port=args.port)
    server.start()
    print(json.dumps({"url": server.url, "weights_sha256": sha256}), flush=True)
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    stop.wait()
    server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
