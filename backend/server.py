"""Stable packaged server command; application/bootstrap implementation lives in apps/ and services/."""

from .apps.server import main as main

if __name__ == "__main__":
    raise SystemExit(main())
