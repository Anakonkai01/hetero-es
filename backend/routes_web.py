"""Compatibility namespace retained during application composition extraction."""

import sys
from .api import web as _implementation

sys.modules[__name__] = _implementation
