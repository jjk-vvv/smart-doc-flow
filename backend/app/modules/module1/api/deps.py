from __future__ import annotations

from fastapi import Depends, Request

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user


async def require_module1_authenticated_user(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    request.state.authenticated_user = current_user
    return current_user


__all__ = ["require_module1_authenticated_user"]
