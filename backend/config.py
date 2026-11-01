"""Compatibility namespace retained during core extraction."""

import sys
from .core import config as _implementation

sys.modules[__name__] = _implementation
