"""Legacy validation HTTP boundary; configuration rules live in services."""

from fastapi import HTTPException
from ..core.errors import ServiceError
from ..services.validation import validate_configuration as _validate_configuration


def validate_configuration(config, current, *, store, runtime, registry, scoped, capabilities):
    try:
        return _validate_configuration(
            config, current, store=store, runtime=runtime, registry=registry, scoped=scoped, capabilities=capabilities
        )
    except ServiceError as error:
        raise HTTPException(error.status_code, error.detail, headers=error.headers) from None
