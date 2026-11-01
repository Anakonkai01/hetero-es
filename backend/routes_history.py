"""Compatibility import retained during the three-layer extraction."""

from .api.history import install_routes as install_routes
from .services.history import DEVICE_EVENTS as DEVICE_EVENTS, message as message, severity as severity
