"""Product UTC timestamp formatting shared by business services."""

from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()
