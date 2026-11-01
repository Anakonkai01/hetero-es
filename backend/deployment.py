"""Compatibility deployment namespace during extraction."""

import sys
from .services import deployment as _implementation

sys.modules[__name__] = _implementation
