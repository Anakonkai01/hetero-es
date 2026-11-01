"""Compatibility module retained during core contract extraction."""

import sys
from .core import device_models as _implementation

sys.modules[__name__] = _implementation
