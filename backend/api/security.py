"""HTTP authentication dependencies."""

from fastapi import Depends, Header, HTTPException


def local_user(accounts):
    def user(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to continue")
        return accounts.current(authorization[7:])

    return user


def workspace_scope(access, user):
    def scoped(current=Depends(user), x_workspace_id: str = Header(default="")):
        return access.scope(current, x_workspace_id)

    return scoped
