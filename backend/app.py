"""Compatibility factory namespace retained during application extraction."""

import sys
from .apps import factory as _implementation

sys.modules[__name__] = _implementation
