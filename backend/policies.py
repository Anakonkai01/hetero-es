"""Compatibility policy namespace retained during service extraction."""

import sys
from .services import policies as _implementation

sys.modules[__name__] = _implementation
