"""Account, workspace and platform HTTP composition."""

from fastapi import Depends
from .accounts import install_routes as install_accounts_routes
from .workspaces import install_routes as install_workspaces_routes
from .operations import install_routes as install_operations_routes
from ..services.access import AccessService


def install_lab_routes(app, store, user, scoped, runtime):
    access = AccessService(store, runtime)

    def active(current=Depends(user)):
        return access.active(current)

    def platform(current=Depends(active)):
        return access.platform(current)

    install_accounts_routes(app, store, user)
    install_workspaces_routes(
        app, store, scoped, active, access.workspace_admin, service_scoped=access.scope, service_active=access.active
    )
    install_operations_routes(app, store, runtime, platform, check_platform=access.platform)
