"""Compatibility namespace retained during application composition extraction."""

import sys
from .apps import monitor as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
