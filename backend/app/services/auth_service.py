from __future__ import annotations

import asyncio
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar

from fastapi import HTTPException, Request, Response, status
from jwt import InvalidTokenError

from app.core.auth_config import AuthSettings
from app.core.auth_notifier import AuthNotifier
from app.repositories.auth_repository import AuthUserRepository
from app.core.auth_security import (
    build_cookie_options,
    create_auth_token,
    decode_auth_token,
    create_session_id,
    hash_password,
    hash_verification_code,
    is_bcrypt_hash,
    is_email,
    is_phone,
    mask_contact,
    normalize_str,
    public_user_payload,
    token_expires_delta,
    verify_password,
    verify_verification_code,
)

if TYPE_CHECKING:
    from app.core.auth_deps import AuthenticatedUser

GENERIC_SEND_CODE_MESSAGE = "If this account is eligible, a verification code has been sent."
_RepositoryResultT = TypeVar("_RepositoryResultT")


@dataclass
class VerificationCodeRecord:
    code: str
    expires_at: int
    user_id: str = ""


@dataclass
class QuotaWindow:
    start_at: int
    count: int


@dataclass
class LoginFailureWindow:
    start_at: int
    count: int
    locked_until: int = 0


class AuthService:
    def __init__(
        self,
        settings: AuthSettings | None = None,
        repository: AuthUserRepository | None = None,
        notifier: AuthNotifier | None = None,
    ) -> None:
        self.settings = settings or AuthSettings.from_env()
        self.repository = repository or AuthUserRepository(self.settings)
        self.notifier = notifier or AuthNotifier(self.settings)
        self._lock = threading.RLock()
        self._verification_codes: dict[str, VerificationCodeRecord] = {}
        self._send_code_contact_window: dict[str, QuotaWindow] = {}
        self._send_code_ip_window: dict[str, QuotaWindow] = {}
        self._send_code_cooldown: dict[str, int] = {}
        self._login_account_window: dict[str, LoginFailureWindow] = {}
        self._login_ip_window: dict[str, LoginFailureWindow] = {}

    async def health_payload(self) -> dict[str, Any]:
        storage_state = self.repository.resolve_storage_state()
        storage_path = storage_state.active_path
        notifier_mode = "disabled"
        if self.settings.sms_provider == "ihuyi":
            notifier_mode = "sms_ihuyi"
        elif self.settings.smtp_host and self.settings.smtp_user and self.settings.smtp_from:
            notifier_mode = "smtp"

        database_error = ""
        database_connected = False
        if self.repository.database_enabled:
            try:
                await self.repository.ensure_ready()
                database_connected = True
            except Exception as exc:
                database_error = f"{type(exc).__name__}: {exc}"
        diagnostics = self.repository.storage.diagnostics()

        users_count = 0
        try:
            users_count = await self.repository.count_users()
        except Exception:
            users_count = len(self.repository._load_users_from_file())

        return {
            "ok": not self.repository.database_enabled or database_connected,
            "service": "unified-auth",
            "cookieName": self.settings.cookie_name,
            "usersFile": str(storage_path),
            "usersFileExists": storage_path.exists(),
            "usersFileMode": storage_state.mode,
            "usersPreferredFile": str(storage_state.preferred_path),
            "usersCount": users_count,
            "secretConfigured": bool(str(self.settings.secret_key or "").strip()),
            "notifierMode": notifier_mode,
            "verificationCacheSize": len(self._verification_codes),
            "databaseEnabled": diagnostics.enabled,
            "databaseConfigured": diagnostics.configured,
            "databaseConnected": database_connected,
            "databaseSchema": diagnostics.schema,
            "databaseLastConnectError": diagnostics.last_connect_error or database_error,
        }

    async def register(self, request: Request, response: Response, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        name = normalize_str(payload.get("name"))
        email = normalize_str(payload.get("email"))
        phone = normalize_str(payload.get("phone"))
        password = normalize_str(payload.get("password"))
        code = normalize_str(payload.get("code"))

        if not name or not email or not phone or not password or not code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing required fields")
        if len(password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters",
            )

        verification_record, matched_contact = await self._find_verification_record("register", phone, email)
        if verification_record is None or not matched_contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please request a verification code first.",
            )
        if self._verification_record_expired(verification_record):
            await self._clear_verification_record("register", matched_contact)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code expired. Please request a new one.",
            )
        if not self._verification_code_matches("register", matched_contact, code, verification_record):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code.",
            )

        existing = await self.repository.find_existing_identity(name, email, phone)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

        new_user = {
            "id": uuid.uuid4().hex,
            "name": name,
            "email": email,
            "phone": phone,
            "password": hash_password(password, self.settings.password_salt_rounds),
            "status": "active",
        }
        await self.repository.create_user(new_user)
        await self._clear_verification_record("register", phone, email)
        await self.repository.touch_last_login(new_user["id"])
        await self._issue_auth_cookie(response, new_user, request)
        await self._append_audit_log(
            request,
            event_type="register_success",
            user_id=new_user["id"],
            payload={"email": email, "phone": phone},
        )
        return {"user": public_user_payload(new_user)}, status.HTTP_201_CREATED

    async def login(self, request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
        account = normalize_str(payload.get("account"))
        password = normalize_str(payload.get("password"))
        if not account or not password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        with self._lock:
            self._cleanup_transient_state()
            retry_after_sec, block_reason = self._check_login_lock(request, account)
        if retry_after_sec > 0:
            await self._append_audit_log(
                request,
                event_type="login_blocked",
                payload={"account": account, "reason": block_reason, "retry_after_sec": retry_after_sec},
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many login attempts. Retry after {retry_after_sec}s.",
            )

        user = await self._run_repository_operation(
            "login.find_user_by_account",
            lambda: self.repository.find_user_by_account(account),
        )
        if user is None:
            with self._lock:
                self._record_login_failure(request, account)
            await self._append_audit_log(
                request,
                event_type="login_failed",
                payload={"account": account, "reason": "not_found"},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if normalize_str(user.get("status")) not in {"", "active"}:
            with self._lock:
                self._record_login_failure(request, account)
            await self._append_audit_log(
                request,
                event_type="login_failed",
                user_id=user["id"],
                payload={"account": account, "reason": "inactive"},
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

        current_password = normalize_str(user.get("password"))
        is_match = False
        if is_bcrypt_hash(current_password):
            is_match = verify_password(password, current_password)
        else:
            is_match = current_password == password
            if is_match:
                upgraded_password_hash = hash_password(password, self.settings.password_salt_rounds)
                await self._run_repository_operation(
                    "login.update_user_password",
                    lambda: self.repository.update_user_password(user["id"], upgraded_password_hash),
                )
                user["password"] = upgraded_password_hash

        if not is_match:
            with self._lock:
                self._record_login_failure(request, account)
            await self._append_audit_log(
                request,
                event_type="login_failed",
                user_id=user["id"],
                payload={"account": account, "reason": "password_mismatch"},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        with self._lock:
            self._clear_login_failures(request, account)
        await self._run_repository_operation(
            "login.touch_last_login",
            lambda: self.repository.touch_last_login(user["id"]),
        )
        try:
            await self._issue_auth_cookie(response, user, request)
        except Exception as exc:
            translated_error = self._translate_auth_backend_exception(exc)
            if translated_error is not None:
                raise translated_error from exc
            raise
        await self._append_audit_log(
            request,
            event_type="login_success",
            user_id=user["id"],
            payload={"account": account},
        )
        return {"user": public_user_payload(user)}

    async def logout(self, request: Request, response: Response) -> dict[str, str]:
        token = request.cookies.get(self.settings.cookie_name)
        if token and self.repository.database_enabled:
            try:
                decoded = self._decode_token(token)
                session_id = normalize_str(decoded.get("sid"))
                if session_id:
                    await self.repository.revoke_session(session_id)
            except HTTPException:
                pass
        cookie_options = build_cookie_options(self.settings)
        response.delete_cookie(
            key=self.settings.cookie_name,
            httponly=True,
            secure=cookie_options.secure,
            samesite=cookie_options.samesite,
        )
        await self._append_audit_log(request, event_type="logout")
        return {"message": "Logged out successfully"}

    async def me(self, request: Request) -> dict[str, Any]:
        user = await self.authenticate_request(request)
        return {"user": public_user_payload(user)}

    async def list_sessions(self, request: Request, current_user: "AuthenticatedUser") -> dict[str, Any]:
        if not self.repository.database_enabled:
            return {
                "sessions": [
                    {
                        "sessionId": normalize_str(current_user.session_id) or "current",
                        "current": True,
                        "ipAddress": self._get_client_ip(request),
                        "userAgent": normalize_str(request.headers.get("user-agent")),
                        "createdAt": None,
                        "lastSeenAt": None,
                        "expiresAt": None,
                        "revokedAt": None,
                        "status": "active",
                    }
                ],
                "supportsPersistentSessions": False,
            }

        sessions = await self.repository.list_sessions_for_user(current_user.user_id)
        serialized = [
            self._serialize_session_record(item, current_session_id=current_user.session_id)
            for item in sessions
        ]
        serialized.sort(key=lambda item: 0 if item["current"] else 1)
        return {
            "sessions": serialized,
            "supportsPersistentSessions": True,
        }

    async def revoke_session_for_user(
        self,
        request: Request,
        current_user: "AuthenticatedUser",
        session_id: str,
    ) -> dict[str, Any]:
        target_session_id = normalize_str(session_id)
        if not target_session_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session id is required")
        if not self.repository.database_enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Persistent session management is unavailable in file storage mode",
            )
        if target_session_id == normalize_str(current_user.session_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use logout to revoke the current session",
            )

        revoked = await self.repository.revoke_session_for_user(current_user.user_id, target_session_id)
        if not revoked:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        await self._append_audit_log(
            request,
            event_type="session_revoked",
            user_id=current_user.user_id,
            payload={"session_id": target_session_id, "scope": "single"},
        )
        return {"message": "Session revoked successfully.", "revokedCount": 1}

    async def revoke_other_sessions(
        self,
        request: Request,
        current_user: "AuthenticatedUser",
    ) -> dict[str, Any]:
        if not self.repository.database_enabled:
            return {"message": "No other persistent sessions to revoke.", "revokedCount": 0}

        revoked_count = await self.repository.revoke_other_sessions_for_user(
            current_user.user_id,
            exclude_session_id=current_user.session_id,
        )
        await self._append_audit_log(
            request,
            event_type="session_revoked",
            user_id=current_user.user_id,
            payload={"session_id": normalize_str(current_user.session_id), "scope": "others", "revoked_count": revoked_count},
        )
        return {
            "message": "Other sessions revoked successfully.",
            "revokedCount": revoked_count,
        }

    async def authenticate_request(self, request: Request) -> dict[str, Any]:
        token = request.cookies.get(self.settings.cookie_name)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        decoded = self._decode_token(token)
        session_id = normalize_str(decoded.get("sid"))

        if self.repository.database_enabled:
            if self.settings.require_session_id_in_db_mode and not session_id:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session id is required")
            if session_id:
                session = await self._run_repository_operation(
                    "authenticate_request.get_session",
                    lambda: self.repository.get_session(session_id),
                )
                if session is None:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session")
                revoked_at = session.get("revoked_at")
                expires_at = session.get("expires_at")
                if revoked_at is not None:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session revoked")
                if isinstance(expires_at, datetime) and expires_at <= datetime.now(UTC):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session expired")
                await self._run_repository_operation(
                    "authenticate_request.touch_session",
                    lambda: self.repository.touch_session(session_id),
                )

            user = await self._run_repository_operation(
                "authenticate_request.get_user_by_id",
                lambda: self.repository.get_user_by_id(normalize_str(decoded.get("id"))),
            )
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if normalize_str(user.get("status")) not in {"", "active"}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
            authenticated_user = dict(user)
            authenticated_user["session_id"] = session_id
            return authenticated_user

        return {
            "id": normalize_str(decoded.get("id")),
            "name": normalize_str(decoded.get("name")),
            "email": normalize_str(decoded.get("email")),
            "phone": normalize_str(decoded.get("phone")),
            "status": "active",
            "session_id": session_id,
        }

    async def send_forgot_code(self, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        contact = normalize_str(payload.get("contact"))
        if not contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please enter phone number or email.",
            )

        with self._lock:
            self._cleanup_transient_state()
            retry_after_sec = self._check_send_code_quota(request, contact)
            if retry_after_sec > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Retry after {retry_after_sec}s.",
                )

        user = await self.repository.find_user_by_contact(contact)
        if user is None:
            return {
                "message": GENERIC_SEND_CODE_MESSAGE,
                "maskedContact": mask_contact(contact),
            }

        code = self._generate_code()
        await self._store_verification_record("forgot", contact, code, user_id=user["id"])

        result = self.notifier.send_forgot_code(contact, code)
        if not result.ok:
            await self._clear_verification_record("forgot", contact)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Verification service temporarily unavailable",
            )

        with self._lock:
            self._mark_send_code_success(contact)

        await self._append_audit_log(
            request,
            event_type="forgot_code_sent",
            user_id=user["id"],
            payload={"contact": contact},
        )
        return {
            "message": GENERIC_SEND_CODE_MESSAGE,
            "maskedContact": mask_contact(contact),
            "devCode": result.dev_code or None,
        }

    async def reset_forgot_password(self, request: Request, payload: dict[str, Any]) -> dict[str, str]:
        contact = normalize_str(payload.get("contact"))
        code = normalize_str(payload.get("code"))
        new_password = normalize_str(payload.get("newPassword"))

        if not contact or not code or not new_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please fill in all required fields.")
        if len(new_password) < 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 6 characters.",
            )

        stored, matched_contact = await self._find_verification_record("forgot", contact)
        if stored is None or not matched_contact:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please request a verification code first.",
            )
        if self._verification_record_expired(stored):
            await self._clear_verification_record("forgot", matched_contact)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code expired. Please request a new one.",
            )
        if not self._verification_code_matches("forgot", matched_contact, code, stored):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code.",
            )

        user_id = normalize_str(stored.get("user_id"))
        user = await self.repository.get_user_by_id(user_id) if user_id else await self.repository.find_user_by_contact(contact)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        await self.repository.update_user_password(
            user["id"],
            hash_password(new_password, self.settings.password_salt_rounds),
        )
        await self.repository.revoke_sessions_for_user(user["id"])
        await self._clear_verification_record("forgot", matched_contact)
        await self._append_audit_log(
            request,
            event_type="password_reset_success",
            user_id=user["id"],
            payload={"contact": contact},
        )
        return {"message": "Password reset successful. Please log in with the new password."}

    async def send_register_code(self, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        contact = normalize_str(payload.get("contact"))
        if not contact or (not is_email(contact) and not is_phone(contact)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please enter a valid email address or phone number.",
            )

        with self._lock:
            self._cleanup_transient_state()
            retry_after_sec = self._check_send_code_quota(request, contact)
            if retry_after_sec > 0:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Retry after {retry_after_sec}s.",
                )

        exists = await self.repository.find_user_by_contact(contact)
        if exists is not None:
            detail = (
                "This email is already registered. Please sign in or reset your password."
                if is_email(contact)
                else "This phone number is already registered. Please sign in or reset your password."
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            )

        code = self._generate_code()
        await self._store_verification_record("register", contact, code)

        result = self.notifier.send_registration_code(contact, code)
        if not result.ok:
            await self._clear_verification_record("register", contact)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Verification service temporarily unavailable",
            )

        with self._lock:
            self._mark_send_code_success(contact)

        await self._append_audit_log(
            request,
            event_type="register_code_sent",
            payload={"contact": contact},
        )
        return {
            "message": GENERIC_SEND_CODE_MESSAGE,
            "maskedContact": mask_contact(contact),
            "devCode": result.dev_code or None,
        }

    async def shutdown(self) -> None:
        await self.repository.shutdown()

    async def _issue_auth_cookie(self, response: Response, user: dict[str, Any], request: Request) -> None:
        session_id = ""
        if self.repository.database_enabled:
            session_id = create_session_id()
            expires_at = datetime.now(UTC) + token_expires_delta(self.settings)
            await self.repository.create_session(
                session_id=session_id,
                user_id=normalize_str(user.get("id")),
                expires_at=expires_at,
                ip_address=self._get_client_ip(request),
                user_agent=normalize_str(request.headers.get("user-agent")),
            )
        token = create_auth_token(user, self.settings, session_id=session_id)
        cookie_options = build_cookie_options(self.settings)
        response.set_cookie(
            key=self.settings.cookie_name,
            value=token,
            httponly=True,
            secure=cookie_options.secure,
            samesite=cookie_options.samesite,
            max_age=cookie_options.max_age,
        )

    async def _find_verification_record(
        self,
        purpose: str,
        *contacts: str,
    ) -> tuple[dict[str, Any] | None, str]:
        normalized_contacts = []
        seen_contacts: set[str] = set()
        for contact in contacts:
            normalized_contact = normalize_str(contact)
            if not normalized_contact or normalized_contact in seen_contacts:
                continue
            normalized_contacts.append(normalized_contact)
            seen_contacts.add(normalized_contact)

        if self.repository.database_enabled:
            for contact in normalized_contacts:
                stored = await self.repository.get_verification_code(purpose=purpose, contact=contact)
                if stored is not None:
                    return stored, contact
            return None, ""

        with self._lock:
            self._cleanup_transient_state()
            for contact in normalized_contacts:
                stored = self._verification_codes.get(contact)
                if stored is not None:
                    return {
                        "code": stored.code,
                        "user_id": stored.user_id,
                        "expires_at": stored.expires_at,
                    }, contact
        return None, ""

    async def _store_verification_record(
        self,
        purpose: str,
        contact: str,
        code: str,
        *,
        user_id: str = "",
    ) -> None:
        if self.repository.database_enabled:
            expires_at = datetime.now(UTC) + self._verification_expires_delta()
            await self.repository.store_verification_code(
                purpose=purpose,
                contact=contact,
                code_hash=hash_verification_code(code, self.settings, purpose=purpose, contact=contact),
                expires_at=expires_at,
                user_id=user_id,
            )
            return

        with self._lock:
            self._verification_codes[normalize_str(contact)] = VerificationCodeRecord(
                code=normalize_str(code),
                expires_at=self._now_ms() + self.settings.verify_code_expires_ms,
                user_id=normalize_str(user_id),
            )

    async def _clear_verification_record(self, purpose: str, *contacts: str) -> None:
        normalized_contacts = [normalize_str(c) for c in contacts if normalize_str(c)]
        if self.repository.database_enabled:
            for contact in normalized_contacts:
                await self.repository.delete_verification_code(purpose=purpose, contact=contact)
            return

        with self._lock:
            for contact in normalized_contacts:
                self._verification_codes.pop(contact, None)

    def _verification_record_expired(self, stored: dict[str, Any]) -> bool:
        expires_at = stored.get("expires_at")
        if isinstance(expires_at, datetime):
            return expires_at <= datetime.now(UTC)
        try:
            return int(expires_at or 0) < self._now_ms()
        except (TypeError, ValueError):
            return True

    def _verification_code_matches(
        self,
        purpose: str,
        contact: str,
        code: str,
        stored: dict[str, Any],
    ) -> bool:
        if self.repository.database_enabled:
            return verify_verification_code(
                code,
                normalize_str(stored.get("code_hash")),
                self.settings,
                purpose=purpose,
                contact=contact,
            )
        return normalize_str(stored.get("code")) == normalize_str(code)

    def _verification_expires_delta(self):
        return timedelta(milliseconds=max(1, int(self.settings.verify_code_expires_ms)))

    def _cleanup_transient_state(self) -> None:
        now = self._now_ms()
        self._verification_codes = {
            key: value
            for key, value in self._verification_codes.items()
            if value.expires_at >= now
        }
        self._send_code_cooldown = {
            key: value
            for key, value in self._send_code_cooldown.items()
            if value >= now
        }
        self._send_code_ip_window = {
            key: value
            for key, value in self._send_code_ip_window.items()
            if now - value.start_at < self.settings.send_code_window_ms
        }
        self._send_code_contact_window = {
            key: value
            for key, value in self._send_code_contact_window.items()
            if now - value.start_at < self.settings.send_code_window_ms
        }
        self._login_account_window = {
            key: value
            for key, value in self._login_account_window.items()
            if value.locked_until >= now or (now - value.start_at) < self.settings.login_failure_window_ms
        }
        self._login_ip_window = {
            key: value
            for key, value in self._login_ip_window.items()
            if value.locked_until >= now or (now - value.start_at) < self.settings.login_failure_window_ms
        }

    def _check_send_code_quota(self, request: Request, contact_key: str) -> int:
        ip_key = self._get_client_ip(request)
        retry_after_sec = self._consume_window_quota(
            self._send_code_ip_window,
            ip_key,
            self.settings.send_code_max_per_ip,
        )
        if retry_after_sec > 0:
            return retry_after_sec

        cooldown_at = self._send_code_cooldown.get(contact_key, 0)
        now = self._now_ms()
        if cooldown_at > now:
            return max(1, int((cooldown_at - now + 999) / 1000))

        return self._consume_window_quota(
            self._send_code_contact_window,
            contact_key,
            self.settings.send_code_max_per_contact,
        )

    def _consume_window_quota(
        self,
        bucket: dict[str, QuotaWindow],
        key: str,
        max_count: int,
    ) -> int:
        now = self._now_ms()
        current = bucket.get(key)
        if current is None or (now - current.start_at) >= self.settings.send_code_window_ms:
            bucket[key] = QuotaWindow(start_at=now, count=1)
            return 0
        if current.count >= max_count:
            retry_after_ms = current.start_at + self.settings.send_code_window_ms - now
            return max(1, int((retry_after_ms + 999) / 1000))
        current.count += 1
        return 0

    def _mark_send_code_success(self, contact_key: str) -> None:
        self._send_code_cooldown[contact_key] = self._now_ms() + self.settings.send_code_cooldown_ms

    def _check_login_lock(self, request: Request, account: str) -> tuple[int, str]:
        account_key = normalize_str(account)
        ip_key = self._get_client_ip(request)
        retry_after_sec = self._window_retry_after(self._login_account_window.get(account_key))
        if retry_after_sec > 0:
            return retry_after_sec, "account_locked"
        retry_after_sec = self._window_retry_after(self._login_ip_window.get(ip_key))
        if retry_after_sec > 0:
            return retry_after_sec, "ip_locked"
        return 0, ""

    def _record_login_failure(self, request: Request, account: str) -> None:
        account_key = normalize_str(account)
        ip_key = self._get_client_ip(request)
        self._consume_login_failure(
            self._login_account_window,
            account_key,
            self.settings.login_max_failures_per_account,
        )
        self._consume_login_failure(
            self._login_ip_window,
            ip_key,
            self.settings.login_max_failures_per_ip,
        )

    def _clear_login_failures(self, request: Request, account: str) -> None:
        account_key = normalize_str(account)
        ip_key = self._get_client_ip(request)
        if account_key:
            self._login_account_window.pop(account_key, None)
        if ip_key:
            self._login_ip_window.pop(ip_key, None)

    def _consume_login_failure(
        self,
        bucket: dict[str, LoginFailureWindow],
        key: str,
        max_count: int,
    ) -> None:
        normalized_key = normalize_str(key)
        if not normalized_key:
            return
        now = self._now_ms()
        current = bucket.get(normalized_key)
        if current is None or (
            current.locked_until < now and (now - current.start_at) >= self.settings.login_failure_window_ms
        ):
            bucket[normalized_key] = LoginFailureWindow(start_at=now, count=1)
            return
        if current.locked_until > 0 and current.locked_until <= now:
            bucket[normalized_key] = LoginFailureWindow(start_at=now, count=1)
            return
        if current.locked_until >= now:
            return
        current.count += 1
        if current.count >= max_count:
            current.locked_until = now + self.settings.login_lock_ms

    def _window_retry_after(self, window: LoginFailureWindow | None) -> int:
        if window is None:
            return 0
        now = self._now_ms()
        if window.locked_until <= now:
            return 0
        return max(1, int((window.locked_until - now + 999) / 1000))

    def _serialize_session_record(self, session: dict[str, Any], *, current_session_id: str = "") -> dict[str, Any]:
        session_id = normalize_str(session.get("session_id"))
        created_at = self._serialize_datetime(session.get("created_at"))
        last_seen_at = self._serialize_datetime(session.get("last_seen_at"))
        expires_value = session.get("expires_at")
        expires_at = self._serialize_datetime(expires_value)
        revoked_at = self._serialize_datetime(session.get("revoked_at"))
        now = datetime.now(UTC)
        if revoked_at:
            status_name = "revoked"
        elif isinstance(expires_value, datetime) and expires_value <= now:
            status_name = "expired"
        else:
            status_name = "active"
        return {
            "sessionId": session_id,
            "current": bool(session_id and session_id == normalize_str(current_session_id)),
            "ipAddress": normalize_str(session.get("ip_address")),
            "userAgent": normalize_str(session.get("user_agent")),
            "createdAt": created_at,
            "lastSeenAt": last_seen_at,
            "expiresAt": expires_at,
            "revokedAt": revoked_at,
            "status": status_name,
        }

    def _decode_token(self, token: str) -> dict[str, Any]:
        try:
            return decode_auth_token(token, self.settings)
        except InvalidTokenError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token") from exc

    async def _run_repository_operation(
        self,
        operation_name: str,
        operation: Callable[[], Awaitable[_RepositoryResultT]],
    ) -> _RepositoryResultT:
        try:
            return await operation()
        except HTTPException:
            raise
        except Exception as exc:
            translated_error = self._translate_auth_backend_exception(exc)
            if translated_error is not None:
                raise translated_error from exc
            raise

    def _translate_auth_backend_exception(self, exc: Exception) -> HTTPException | None:
        if not self.repository.database_enabled:
            return None

        is_connectivity_error = isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError))
        if not is_connectivity_error:
            message = str(exc or "").strip().lower()
            connectivity_markers = (
                "auth database",
                "database connection",
                "connection refused",
                "connection timeout",
                "no valid auth database connection candidates",
                "pool is not available",
                "create_pool",
                "asyncpg",
            )
            is_connectivity_error = any(marker in message for marker in connectivity_markers)
        if not is_connectivity_error:
            return None

        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth database is temporarily unavailable. Please retry shortly.",
            headers={"Retry-After": "3"},
        )

    async def _append_audit_log(
        self,
        request: Request | None,
        *,
        event_type: str,
        user_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self.repository.database_enabled:
            return
        try:
            await self.repository.append_audit_log(
                event_type=event_type,
                user_id=user_id,
                ip_address=self._get_client_ip(request),
                user_agent=normalize_str(request.headers.get("user-agent")) if request else "",
                payload=payload,
            )
        except Exception:
            # Audit logs must never break the main auth flow.
            pass

    @staticmethod
    def _generate_code() -> str:
        return str(secrets.randbelow(900000) + 100000)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _serialize_datetime(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat()
        return None

    @staticmethod
    def _get_client_ip(request: Request | None) -> str:
        if request is None:
            return ""
        forwarded_for = normalize_str(request.headers.get("x-forwarded-for"))
        if forwarded_for:
            return normalize_str(forwarded_for.split(",", 1)[0])
        if request.client and request.client.host:
            return normalize_str(request.client.host)
        return "unknown"


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService()
