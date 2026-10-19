"""Private Server monitor: JSON lines, no CUDA; stdin EOF owns its lifetime."""

import argparse
import json
from pathlib import Path
import signal
import sys
import threading
from heteroes.product.telemetry import TelemetrySampler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--storage", type=Path)
    p.add_argument("--energy-state", type=Path)
    args = p.parse_args()
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    stop = threading.Event()

    def lifetime():
        sys.stdin.buffer.read()
        stop.set()

    threading.Thread(target=lifetime, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    sampler = TelemetrySampler(
        args.state, args.storage, energy_directory=args.energy_state or Path.home() / ".local/share/heteroes-power"
    )
    while not stop.is_set():
        try:
            observation = sampler.sample()
            print(
                json.dumps({"observation": observation, "history": list(sampler.history)}, allow_nan=False), flush=True
            )
        except (OSError, ValueError):
            pass
        stop.wait(3)


if __name__ == "__main__":
    main()
