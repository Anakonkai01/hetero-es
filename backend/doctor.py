"""Compatibility doctor namespace and CLI during extraction."""

import sys
from .services import doctor as _implementation
from .apps.doctor import main

_implementation.main = main
if __name__ == "__main__":
    raise SystemExit(main())
else:
    sys.modules[__name__] = _implementation
