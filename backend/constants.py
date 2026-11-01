"""Compatibility module retained during core contract extraction."""

import sys
from .core import constants as _implementation

sys.modules[__name__] = _implementation
