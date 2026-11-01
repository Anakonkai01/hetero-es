"""Compatibility module retained during database-layer extraction."""

import sys
from .db import migrations as _implementation

sys.modules[__name__] = _implementation
