from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user

from .endpoints.files import router as files_router


async def _inject_authenticated_user(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
) -> AuthenticatedUser:
    request.state.authenticated_user = current_user
    return current_user


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(files_router, dependencies=[Depends(_inject_authenticated_user)])
    return router


router = build_router()

__all__ = ["build_router", "router"]
