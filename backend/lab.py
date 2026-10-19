"""Identity and membership operations, independent of runtime numerical state."""
from .routes_accounts import install_routes as install_accounts_routes
from .routes_workspaces import install_routes as install_workspaces_routes
from .routes_operations import install_routes as install_operations_routes
from .policies import active_profile, platform_profile

from fastapi import Depends, HTTPException





















def install_lab_routes(app, store, user, scoped, runtime):
    def active(current=Depends(user)):
        return active_profile(store, current, 'Your account is awaiting approval or is restricted')

    def platform(current=Depends(active)):
        return platform_profile(current, 'Platform administrator permission required')

    def workspace_admin(workspace_id,current):
        fresh = scoped(current,workspace_id)
        if fresh['workspaceRole']!='ADMIN':
            raise HTTPException(403,'Workspace administrator permission required')
        return fresh

    install_accounts_routes(app, store, user)
    install_workspaces_routes(app, store, scoped, active, workspace_admin)
    install_operations_routes(app, store, runtime, platform)
