"""Compatibility import retained during the three-layer extraction."""

from .api.notifications import install_routes as install_notification_routes
from .services.notifications import (
    MAX_LIMIT as MAX_LIMIT,
    MAX_IDS as MAX_IDS,
    RUN_KINDS as RUN_KINDS,
    ACCOUNT_KINDS as ACCOUNT_KINDS,
    Notifications as Notifications,
    _stamp as _stamp,
    _epoch as _epoch,
)
