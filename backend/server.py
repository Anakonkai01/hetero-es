"""Compatibility packaged server exports and command entrypoint."""

from .core.server_models import Bootstrap as Bootstrap
from .services.bootstrap import initialize as initialize
from .apps.server import main as main

if __name__ == "__main__":
    raise SystemExit(main())
