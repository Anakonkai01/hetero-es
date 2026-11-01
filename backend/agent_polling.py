"""Compatibility module retained during the business-layer extraction."""

import sys
from .services import agent_polling as _implementation

sys.modules[__name__] = _implementation
