"""Compatibility namespace retained during core extraction."""

import sys
from .core import throttle as _implementation

sys.modules[__name__] = _implementation
