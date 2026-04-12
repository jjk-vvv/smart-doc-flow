from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.domain.auth import (
    ForgotResetRequest,
    LoginRequest,
    RegisterRequest,
    SessionRevokeResponse,
    SendCodeRequest,
    AuthSessionListResponse,
)
from app.services.auth_service import AuthService, get_auth_service


def build_router() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/api/auth/health")
    async def auth_health(
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.health_payload()

    @router.post("/api/register")
    async def register(
        request: Request,
        payload: RegisterRequest,
        response: Response,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        body, status_code = await auth_service.register(request, response, payload.model_dump())
        return JSONResponse(status_code=status_code, content=body, headers=dict(response.headers))

    @router.post("/api/login")
    async def login(
        request: Request,
        payload: LoginRequest,
        response: Response,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        body = await auth_service.login(request, response, payload.model_dump())
        return JSONResponse(status_code=200, content=body, headers=dict(response.headers))

    @router.post("/api/logout")
    async def logout(
        request: Request,
        response: Response,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        body = await auth_service.logout(request, response)
        return JSONResponse(status_code=200, content=body, headers=dict(response.headers))

    @router.get("/api/me")
    async def me(
        request: Request,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.me(request)

    @router.get("/api/sessions", response_model=AuthSessionListResponse)
    async def list_sessions(
        request: Request,
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.list_sessions(request, current_user)

    @router.post("/api/sessions/revoke-others", response_model=SessionRevokeResponse)
    async def revoke_other_sessions(
        request: Request,
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.revoke_other_sessions(request, current_user)

    @router.delete("/api/sessions/{session_id}", response_model=SessionRevokeResponse)
    async def revoke_session(
        session_id: str,
        request: Request,
        current_user: AuthenticatedUser = Depends(require_authenticated_user),
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.revoke_session_for_user(request, current_user, session_id)

    @router.post("/api/forgot/send-code")
    async def send_forgot_code(
        request: Request,
        payload: SendCodeRequest,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.send_forgot_code(request, payload.model_dump())

    @router.post("/api/forgot/reset")
    async def reset_forgot_password(
        request: Request,
        payload: ForgotResetRequest,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.reset_forgot_password(request, payload.model_dump())

    @router.post("/api/register/send-code")
    async def send_register_code(
        request: Request,
        payload: SendCodeRequest,
        auth_service: AuthService = Depends(get_auth_service),
    ):
        return await auth_service.send_register_code(request, payload.model_dump())

    return router


router = build_router()
