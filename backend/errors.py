"""Shared runtime admission errors."""


class RuntimeRejected(Exception):
    """The runtime definitively rejected a new configuration without launching it."""
