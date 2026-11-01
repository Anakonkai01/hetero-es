"""Compatibility namespace retained during application composition extraction."""

import sys
from .core import writer_lock as _implementation

sys.modules[__name__] = _implementation
