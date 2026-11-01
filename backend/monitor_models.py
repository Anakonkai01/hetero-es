"""Compatibility namespace retained during core extraction."""

import sys
from .core import monitor_models as _implementation

sys.modules[__name__] = _implementation
