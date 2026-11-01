"""Export the product routing contract without reading private configuration or any existing database."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .factory import create_app
from .routing import inventory
from ..services.devices import AgentRuntime
from ..storage.local_backend import LocalBackend


def contract():
    with TemporaryDirectory(prefix="heteroes-route-export-") as directory:
        root = Path(directory)
        web, downloads = root / "web", root / "downloads"
        (web / "assets").mkdir(parents=True)
        downloads.mkdir()
        (web / "index.html").write_text("<!doctype html><title>Route inventory</title>")
        storage = LocalBackend(root / "objects", root / "signing.key", "http://127.0.0.1:18052")
        app = create_app(
            root / "product.sqlite",
            {},
            AgentRuntime(storage),
            dispatch=False,
            web_directory=web,
            downloads_directory=downloads,
        )
        try:
            result = inventory(app)
            result.pop("service")
            return {"version": 1, **result}
        finally:
            app.state.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit the machine-readable routing contract")
    parser.parse_args()
    print(json.dumps(contract(), indent=2))


if __name__ == "__main__":
    main()
