"""Compatibility import retained during the three-layer extraction."""

from .api.templates import install_routes as install_template_routes
from .api.templates import clean_config as clean_config
from .services.templates import (
    MAX_PER_WORKSPACE as MAX_PER_WORKSPACE,
    INTEGERS as INTEGERS,
    FLOATS as FLOATS,
    NULLABLE as NULLABLE,
    CHOICES as CHOICES,
    SHORT_TEXT as SHORT_TEXT,
)
