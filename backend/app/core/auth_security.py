from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.auth_config import AuthSettings

BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$")
TOKEN_EXPIRES_RE = re.compile(r"^(?P<count>\d+)\s*(?P<unit>[dhms]?)$", re.IGNORECASE)


@dataclass(frozen=True)
class AuthCookieOptions:
    secure: bool
    httponly: bool
    samesite: str
    max_age: int


def normalize_str(value: Any) -> str:
    return str(value or "").strip()


def is_bcrypt_hash(value: Any) -> bool:
    return bool(BCRYPT_HASH_RE.match(normalize_str(value)))


def is_phone(value: str) -> bool:
    return bool(PHONE_RE.match(normalize_str(value)))


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(normalize_str(value)))


def public_user_payload(user: dict[str, Any]) -> dict[str, str]:
    user_id = normalize_str(user.get("id"))
    return {
        "id": user_id,
        "name": normalize_str(user.get("name")),
        "email": normalize_str(user.get("email")),
        "phone": normalize_str(user.get("phone")),
        "status": normalize_str(user.get("status")) or "active",
        "tenantId": user_id,
    }


def mask_contact(contact: str) -> str:
    text = normalize_str(contact)
    if "@" in text:
        local_part, _, domain = text.partition("@")
        return f"{local_part[:2]}***@{domain}" if domain else f"{local_part[:2]}***"
    if len(text) >= 7:
        return f"{text[:3]}****{text[-4:]}"
    return text


def hash_password(password: str, salt_rounds: int) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=max(4, int(salt_rounds))),
    ).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _parse_token_expires(raw_value: str) -> timedelta:
    matched = TOKEN_EXPIRES_RE.match(normalize_str(raw_value))
    if not matched:
        return timedelta(days=7)
    count = max(1, int(matched.group("count")))
    unit = matched.group("unit").lower() or "s"
    if unit == "d":
        return timedelta(days=count)
    if unit == "h":
        return timedelta(hours=count)
    if unit == "m":
        return timedelta(minutes=count)
    return timedelta(seconds=count)


def build_cookie_options(settings: AuthSettings) -> AuthCookieOptions:
    return AuthCookieOptions(
        secure=settings.is_prod,
        httponly=True,
        samesite="strict" if settings.is_prod else "lax",
        max_age=settings.cookie_max_age_days * 24 * 60 * 60,
    )


def token_expires_delta(settings: AuthSettings) -> timedelta:
    return _parse_token_expires(settings.token_expires_in)


def create_session_id() -> str:
    return uuid.uuid4().hex


def hash_verification_code(code: str, settings: AuthSettings, *, purpose: str, contact: str) -> str:
    payload = f"{normalize_str(purpose)}::{normalize_str(contact)}::{normalize_str(code)}"
    return hashlib.sha256(f"{normalize_str(settings.secret_key)}::{payload}".encode("utf-8")).hexdigest()


def verify_verification_code(
    code: str,
    hashed_code: str,
    settings: AuthSettings,
    *,
    purpose: str,
    contact: str,
) -> bool:
    expected = hash_verification_code(code, settings, purpose=purpose, contact=contact)
    return hmac.compare_digest(normalize_str(expected), normalize_str(hashed_code))


def create_auth_token(user: dict[str, Any], settings: AuthSettings, *, session_id: str = "") -> str:
    now = datetime.now(UTC)
    expires_delta = token_expires_delta(settings)
    payload = {
        "id": normalize_str(user.get("id")),
        "name": normalize_str(user.get("name")),
        "email": normalize_str(user.get("email")),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if normalize_str(session_id):
        payload["sid"] = normalize_str(session_id)
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_auth_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
