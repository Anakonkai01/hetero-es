"""Compatibility namespace retained during core extraction."""

import sys
from .core import request_models as _implementation
from heteroes.catalog import DEFAULT_SCHEDULER_POLICY as DEFAULT_SCHEDULER_POLICY, SYNC_MODES as SYNC_MODES

sys.modules[__name__] = _implementation
