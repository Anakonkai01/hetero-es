"""Compatibility namespace retained during application composition extraction."""

import sys
from .api import live as _implementation

sys.modules[__name__] = _implementation
