"""HTTP authentication dependencies."""

from fastapi import Header, HTTPException


def local_user(accounts):
    def user(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Sign in to continue")
        return accounts.current(authorization[7:])

    return user
