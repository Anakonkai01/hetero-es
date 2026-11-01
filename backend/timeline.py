"""Compatibility namespace retained during application composition extraction."""

import sys
from .services import timeline as _implementation

sys.modules[__name__] = _implementation
