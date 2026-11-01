"""Compatibility namespace retained during core extraction."""

import sys
from .core import addresses as _implementation

sys.modules[__name__] = _implementation
