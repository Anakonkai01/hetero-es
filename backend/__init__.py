"""CPU product service; use the shared runtime package in a source checkout."""

from pathlib import Path
import sys

_source = Path(__file__).resolve().parents[1] / "runtime" / "src"
if _source.is_dir():
    sys.path.insert(0, str(_source))
