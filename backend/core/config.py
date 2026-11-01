"""Read private configuration on demand so rotated public URLs are observed."""

import json
import os
from pathlib import Path


def load_config(root=None, *, optional=False):
    root = root or os.environ.get("HETEROES_PRIVATE_CONFIG")
    if not root:
        if optional:
            return {}
        raise ValueError("Set HETEROES_PRIVATE_CONFIG to the lab configuration directory")
    try:
        return json.loads((Path(root) / "config.json").read_text())
    except (OSError, ValueError):
        if optional:
            return {}
        raise
