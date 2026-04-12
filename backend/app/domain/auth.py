from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class PublicUser(AuthModel):
    id: str
    name: str
    email: str
    phone: str
    status: str
    tenantId: str


class UserEnvelope(AuthModel):
    user: PublicUser


class LoginRequest(AuthModel):
    account: str
    password: str


class RegisterRequest(AuthModel):
    name: str
    email: str
    phone: str
    password: str
    code: str


class SendCodeRequest(AuthModel):
    contact: str


class ForgotResetRequest(AuthModel):
    contact: str
    code: str
    newPassword: str


class MessageResponse(AuthModel):
    message: str


class SendCodeResponse(AuthModel):
    message: str
    maskedContact: str | None = None
    devCode: str | None = None


class AuthSessionItem(AuthModel):
    sessionId: str
    current: bool
    ipAddress: str
    userAgent: str
    createdAt: str | None = None
    lastSeenAt: str | None = None
    expiresAt: str | None = None
    revokedAt: str | None = None
    status: str


class AuthSessionListResponse(AuthModel):
    sessions: list[AuthSessionItem]
    supportsPersistentSessions: bool = True


class SessionRevokeResponse(AuthModel):
    message: str
    revokedCount: int = 0
