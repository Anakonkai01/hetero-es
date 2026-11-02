"""Stable desktop doctor command; implementation lives in apps/ and services/."""

from .apps.doctor import main as main

if __name__ == "__main__":
    raise SystemExit(main())
