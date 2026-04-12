from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.auth_security import normalize_str
from app.services.auth_service import AuthService, get_auth_service


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    name: str
    email: str
    phone: str
    status: str
    session_id: str = ""

    @property
    def tenant_id(self) -> str:
        return self.user_id

    def to_forward_headers(self) -> dict[str, str]:
        headers = {
            "X-Authenticated-User-Id": self.user_id,
            "X-Authenticated-Tenant-Id": self.tenant_id,
            "X-Authenticated-User-Name": self.name,
            "X-Authenticated-User-Email": self.email,
        }
        if self.phone:
            headers["X-Authenticated-User-Phone"] = self.phone
        if self.session_id:
            headers["X-Authenticated-Session-Id"] = self.session_id
        return headers


async def require_authenticated_user(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUser:
    authenticated = await auth_service.authenticate_request(request)
    return AuthenticatedUser(
        user_id=normalize_str(authenticated.get("id")),
        name=normalize_str(authenticated.get("name")),
        email=normalize_str(authenticated.get("email")),
        phone=normalize_str(authenticated.get("phone")),
        status=normalize_str(authenticated.get("status")) or "active",
        session_id=normalize_str(authenticated.get("session_id")),
    )


__all__ = [
    "AuthenticatedUser",
    "require_authenticated_user",
]
