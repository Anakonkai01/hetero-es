"""Public compatibility namespace for filesystem storage and instrumentation."""

import sys
from .storage import local_backend as _implementation

sys.modules[__name__] = _implementation
