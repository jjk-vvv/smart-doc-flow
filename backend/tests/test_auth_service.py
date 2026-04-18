from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.core.auth_config import AuthSettings
from app.core.auth_security import create_auth_token, is_bcrypt_hash, verify_password
from app.services.auth_service import AuthService


class _DummyNotifier:
    def __init__(self, *, ok: bool = True, dev_code: str = "") -> None:
        self.ok = ok
        self.dev_code = dev_code
        self.registration_codes: list[dict[str, str]] = []
        self.forgot_codes: list[dict[str, str]] = []

    def send_registration_code(self, contact: str, code: str):
        self.registration_codes.append({"contact": str(contact), "code": str(code)})
        return SimpleNamespace(ok=self.ok, error="" if self.ok else "send_failed", dev_code=self.dev_code)

    def send_forgot_code(self, contact: str, code: str):
        self.forgot_codes.append({"contact": str(contact), "code": str(code)})
        return SimpleNamespace(ok=self.ok, error="" if self.ok else "send_failed", dev_code=self.dev_code)


class FakeAuthRepository:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        users: list[dict[str, str]] | None = None,
        database_enabled: bool = False,
    ) -> None:
        self.settings = settings
        self.database_enabled = database_enabled
        self.users = {
            str(user.get("id") or ""): {
                "status": "active",
                **user,
            }
            for user in (users or [])
        }
        self.verification_codes: dict[tuple[str, str], dict[str, object]] = {}
        self.audit_logs: list[dict[str, object]] = []
        self.revoked_user_ids: list[str] = []
        self.last_login_user_ids: list[str] = []
        self.created_sessions: list[dict[str, object]] = []
        self.session_rows: dict[str, dict[str, object]] = {}

    async def find_user_by_account(self, account: str) -> dict[str, str] | None:
        normalized_account = str(account or "").strip()
        for user in self.users.values():
            if normalized_account in {
                str(user.get("email") or "").strip(),
                str(user.get("phone") or "").strip(),
                str(user.get("name") or "").strip(),
            }:
                return dict(user)
        return None

    async def find_user_by_contact(self, contact: str) -> dict[str, str] | None:
        normalized_contact = str(contact or "").strip()
        for user in self.users.values():
            if normalized_contact in {
                str(user.get("email") or "").strip(),
                str(user.get("phone") or "").strip(),
            }:
                return dict(user)
        return None

    async def find_existing_identity(self, name: str, email: str, phone: str) -> dict[str, str] | None:
        normalized_name = str(name or "").strip()
        normalized_email = str(email or "").strip()
        normalized_phone = str(phone or "").strip()
        for user in self.users.values():
            if normalized_name and normalized_name == str(user.get("name") or "").strip():
                return dict(user)
            if normalized_email and normalized_email == str(user.get("email") or "").strip():
                return dict(user)
            if normalized_phone and normalized_phone == str(user.get("phone") or "").strip():
                return dict(user)
        return None

    async def get_user_by_id(self, user_id: str) -> dict[str, str] | None:
        user = self.users.get(str(user_id or "").strip())
        return dict(user) if user else None

    async def create_user(self, user: dict[str, str]) -> dict[str, str]:
        normalized_user = {
            "status": "active",
            **dict(user or {}),
        }
        user_id = str(normalized_user.get("id") or "").strip()
        if user_id:
            self.users[user_id] = dict(normalized_user)
        return dict(normalized_user)

    async def update_user_password(self, user_id: str, password_hash: str) -> None:
        normalized_user_id = str(user_id or "").strip()
        if normalized_user_id in self.users:
            self.users[normalized_user_id]["password"] = password_hash

    async def touch_last_login(self, user_id: str) -> None:
        self.last_login_user_ids.append(str(user_id or "").strip())

    async def create_session(
        self,
        *,
        session_id: str,
        user_id: str,
        expires_at,
        ip_address: str,
        user_agent: str,
    ) -> None:
        self.created_sessions.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "expires_at": expires_at,
                "ip_address": ip_address,
                "user_agent": user_agent,
            }
        )
        self.session_rows[str(session_id)] = {
            "session_id": str(session_id),
            "user_id": str(user_id),
            "expires_at": expires_at,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": datetime.now(UTC),
            "last_seen_at": datetime.now(UTC),
            "revoked_at": None,
        }

    async def list_sessions_for_user(self, user_id: str) -> list[dict[str, object]]:
        normalized_user_id = str(user_id or "").strip()
        rows = [
            dict(item)
            for item in self.session_rows.values()
            if str(item.get("user_id") or "").strip() == normalized_user_id
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    async def get_session(self, session_id: str) -> dict[str, object] | None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return None
        row = self.session_rows.get(normalized_session_id)
        return dict(row) if row else None

    async def touch_session(self, session_id: str) -> None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        row = self.session_rows.get(normalized_session_id)
        if row is None:
            return
        row["last_seen_at"] = datetime.now(UTC)

    async def store_verification_code(
        self,
        *,
        purpose: str,
        contact: str,
        code_hash: str,
        expires_at,
        user_id: str = "",
    ) -> None:
        self.verification_codes[(purpose, contact)] = {
            "purpose": purpose,
            "contact": contact,
            "code_hash": code_hash,
            "user_id": user_id,
            "expires_at": expires_at,
        }

    async def get_verification_code(self, *, purpose: str, contact: str) -> dict[str, object] | None:
        stored = self.verification_codes.get((purpose, contact))
        return dict(stored) if stored else None

    async def delete_verification_code(self, *, purpose: str, contact: str) -> None:
        self.verification_codes.pop((purpose, contact), None)

    async def revoke_sessions_for_user(self, user_id: str) -> None:
        normalized_user_id = str(user_id or "").strip()
        self.revoked_user_ids.append(normalized_user_id)
        for session in self.session_rows.values():
            if str(session.get("user_id") or "").strip() != normalized_user_id:
                continue
            if session.get("revoked_at") is None:
                session["revoked_at"] = datetime.now(UTC)

    async def revoke_session_for_user(self, user_id: str, session_id: str) -> bool:
        normalized_user_id = str(user_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        session = self.session_rows.get(normalized_session_id)
        if not session:
            return False
        if str(session.get("user_id") or "").strip() != normalized_user_id:
            return False
        if session.get("revoked_at") is None:
            session["revoked_at"] = datetime.now(UTC)
        return True

    async def revoke_other_sessions_for_user(self, user_id: str, *, exclude_session_id: str = "") -> int:
        normalized_user_id = str(user_id or "").strip()
        normalized_exclude_session_id = str(exclude_session_id or "").strip()
        count = 0
        for session_id, session in self.session_rows.items():
            if str(session.get("user_id") or "").strip() != normalized_user_id:
                continue
            if normalized_exclude_session_id and session_id == normalized_exclude_session_id:
                continue
            if session.get("revoked_at") is not None:
                continue
            session["revoked_at"] = datetime.now(UTC)
            count += 1
        return count

    async def append_audit_log(
        self,
        *,
        event_type: str,
        user_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        payload: dict[str, object] | None = None,
    ) -> None:
        self.audit_logs.append(
            {
                "event_type": event_type,
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "payload": payload or {},
            }
        )


def _auth_settings(
    users_file: Path,
    *,
    database_enabled: bool = False,
    login_max_failures_per_account: int = 5,
    login_max_failures_per_ip: int = 20,
    login_failure_window_ms: int = 900000,
    login_lock_ms: int = 900000,
) -> AuthSettings:
    return AuthSettings(
        secret_key="test-secret",
        token_expires_in="7d",
        cookie_name="token",
        cookie_max_age_days=7,
        password_salt_rounds=10,
        verify_code_expires_ms=300000,
        send_code_window_ms=600000,
        send_code_max_per_contact=5,
        send_code_max_per_ip=20,
        send_code_cooldown_ms=60000,
        login_failure_window_ms=login_failure_window_ms,
        login_max_failures_per_account=login_max_failures_per_account,
        login_max_failures_per_ip=login_max_failures_per_ip,
        login_lock_ms=login_lock_ms,
        is_prod=False,
        users_file=users_file,
        sms_provider="",
        ihuyi_api_id="",
        ihuyi_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_secure=False,
        smtp_user="",
        smtp_pass="",
        smtp_from="",
        database_enabled=database_enabled,
        database_dsn="",
        database_schema="auth",
        db_connect_timeout_sec=3.0,
        db_schema_timeout_sec=8.0,
        db_pool_min_size=1,
        db_pool_max_size=10,
    )


def _request(ip: str = "127.0.0.1", path: str = "/api/login") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [(b"user-agent", b"pytest")],
        "client": (ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _request_with_cookie(token: str, *, ip: str = "127.0.0.1", path: str = "/api/me") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [
            (b"user-agent", b"pytest"),
            (b"cookie", f"token={token}".encode("utf-8")),
        ],
        "client": (ip, 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def test_reset_forgot_password_revokes_existing_sessions(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "old-password",
                "status": "active",
            }
        ],
    )
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    asyncio.run(
        service._store_verification_record(
            "forgot",
            "tester@example.com",
            "123456",
            user_id="user-1",
        )
    )

    result = asyncio.run(
        service.reset_forgot_password(
            _request(path="/api/forgot/reset"),
            {
                "contact": "tester@example.com",
                "code": "123456",
                "newPassword": "new-password-123",
            },
        )
    )

    updated_user = repository.users["user-1"]
    assert result["message"].startswith("Password reset successful")
    assert repository.revoked_user_ids == ["user-1"]
    assert is_bcrypt_hash(str(updated_user["password"])) is True
    assert verify_password("new-password-123", str(updated_user["password"])) is True
    assert repository.verification_codes == {}


def test_login_blocks_after_repeated_failures(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        login_max_failures_per_account=3,
        login_max_failures_per_ip=10,
        login_failure_window_ms=300000,
        login_lock_ms=120000,
    )
    repository = FakeAuthRepository(
        settings,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "correct-password",
                "status": "active",
            }
        ],
    )
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())
    request = _request()

    for _ in range(3):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                service.login(
                    request,
                    Response(),
                    {"account": "tester@example.com", "password": "wrong-password"},
                )
            )
        assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            service.login(
                request,
                Response(),
                {"account": "tester@example.com", "password": "correct-password"},
            )
        )

    assert exc_info.value.status_code == 429
    assert "Too many login attempts" in str(exc_info.value.detail)


def test_login_success_returns_enriched_user_payload(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
    )
    repository = FakeAuthRepository(
        settings,
        users=[
            {
                "id": "user-7",
                "name": "FlowUser",
                "email": "flow@example.com",
                "phone": "13800000000",
                "password": "plain-password",
                "status": "active",
            }
        ],
    )
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    result = asyncio.run(
        service.login(
            _request(),
            Response(),
            {"account": "flow@example.com", "password": "plain-password"},
        )
    )

    assert result["user"]["id"] == "user-7"
    assert result["user"]["email"] == "flow@example.com"
    assert result["user"]["phone"] == "13800000000"
    assert result["user"]["status"] == "active"
    assert result["user"]["tenantId"] == "user-7"


def test_send_register_code_rejects_existing_email_with_clear_error(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
    )
    repository = FakeAuthRepository(
        settings,
        users=[
            {
                "id": "user-8",
                "name": "ExistingUser",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "plain-password",
                "status": "active",
            }
        ],
    )
    notifier = _DummyNotifier()
    service = AuthService(settings=settings, repository=repository, notifier=notifier)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            service.send_register_code(
                _request(path="/api/register/send-code"),
                {"contact": "tester@example.com"},
            )
        )

    assert exc_info.value.status_code == 409
    assert "already registered" in str(exc_info.value.detail)
    assert notifier.registration_codes == []


def test_send_register_code_sends_email_for_new_contact(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
    )
    repository = FakeAuthRepository(settings)
    notifier = _DummyNotifier()
    service = AuthService(settings=settings, repository=repository, notifier=notifier)

    result = asyncio.run(
        service.send_register_code(
            _request(path="/api/register/send-code"),
            {"contact": "fresh-user@example.com"},
        )
    )

    assert result["maskedContact"] == "fr***@example.com"
    assert notifier.registration_codes
    assert notifier.registration_codes[0]["contact"] == "fresh-user@example.com"
    assert "fresh-user@example.com" in service._verification_codes


def test_list_sessions_returns_current_session_first(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )
    now = datetime.now(UTC)
    repository.session_rows = {
        "sess-old": {
            "session_id": "sess-old",
            "user_id": "user-1",
            "ip_address": "127.0.0.2",
            "user_agent": "old-browser",
            "created_at": now - timedelta(hours=3),
            "last_seen_at": now - timedelta(hours=1),
            "expires_at": now + timedelta(days=1),
            "revoked_at": None,
        },
        "sess-current": {
            "session_id": "sess-current",
            "user_id": "user-1",
            "ip_address": "127.0.0.1",
            "user_agent": "current-browser",
            "created_at": now - timedelta(hours=2),
            "last_seen_at": now - timedelta(minutes=5),
            "expires_at": now + timedelta(days=1),
            "revoked_at": None,
        },
        "sess-revoked": {
            "session_id": "sess-revoked",
            "user_id": "user-1",
            "ip_address": "127.0.0.3",
            "user_agent": "revoked-browser",
            "created_at": now - timedelta(hours=4),
            "last_seen_at": now - timedelta(hours=2),
            "expires_at": now + timedelta(days=1),
            "revoked_at": now - timedelta(minutes=30),
        },
    }
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    result = asyncio.run(
        service.list_sessions(
            _request(path="/api/sessions"),
            type(
                "_CurrentUser",
                (),
                {"user_id": "user-1", "session_id": "sess-current"},
            )(),
        )
    )

    assert result["supportsPersistentSessions"] is True
    assert result["sessions"][0]["sessionId"] == "sess-current"
    assert result["sessions"][0]["current"] is True
    assert result["sessions"][0]["status"] == "active"
    assert any(item["sessionId"] == "sess-revoked" and item["status"] == "revoked" for item in result["sessions"])


def test_revoke_other_sessions_keeps_current_session(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )
    now = datetime.now(UTC)
    repository.session_rows = {
        "sess-current": {
            "session_id": "sess-current",
            "user_id": "user-1",
            "ip_address": "127.0.0.1",
            "user_agent": "current-browser",
            "created_at": now - timedelta(hours=2),
            "last_seen_at": now - timedelta(minutes=5),
            "expires_at": now + timedelta(days=1),
            "revoked_at": None,
        },
        "sess-other": {
            "session_id": "sess-other",
            "user_id": "user-1",
            "ip_address": "127.0.0.2",
            "user_agent": "other-browser",
            "created_at": now - timedelta(hours=3),
            "last_seen_at": now - timedelta(hours=1),
            "expires_at": now + timedelta(days=1),
            "revoked_at": None,
        },
    }
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    result = asyncio.run(
        service.revoke_other_sessions(
            _request(path="/api/sessions/revoke-others"),
            type(
                "_CurrentUser",
                (),
                {"user_id": "user-1", "session_id": "sess-current"},
            )(),
        )
    )

    assert result["revokedCount"] == 1
    assert repository.session_rows["sess-current"]["revoked_at"] is None
    assert repository.session_rows["sess-other"]["revoked_at"] is not None


def test_revoke_session_rejects_current_session(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            service.revoke_session_for_user(
                _request(path="/api/sessions/sess-current"),
                type(
                    "_CurrentUser",
                    (),
                    {"user_id": "user-1", "session_id": "sess-current"},
                )(),
                "sess-current",
            )
        )

    assert exc_info.value.status_code == 400
    assert "Use logout" in str(exc_info.value.detail)


def test_authenticate_request_requires_sid_in_database_mode(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())
    token_without_sid = create_auth_token(repository.users["user-1"], settings)
    request = _request_with_cookie(token_without_sid, path="/api/me")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.authenticate_request(request))

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "Session id is required"


def test_login_returns_503_when_auth_database_is_temporarily_unavailable(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )

    async def _raise_db_error(account: str):
        del account
        raise RuntimeError("No valid auth database connection candidates")

    repository.find_user_by_account = _raise_db_error  # type: ignore[method-assign]
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            service.login(
                _request(),
                Response(),
                {"account": "tester@example.com", "password": "secret"},
            )
        )

    assert exc_info.value.status_code == 503
    assert str(exc_info.value.detail) == "Auth database is temporarily unavailable. Please retry shortly."


def test_authenticate_request_returns_503_when_session_store_is_unavailable(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=True,
    )
    repository = FakeAuthRepository(
        settings,
        database_enabled=True,
        users=[
            {
                "id": "user-1",
                "name": "Tester",
                "email": "tester@example.com",
                "phone": "13900000000",
                "password": "secret",
                "status": "active",
            }
        ],
    )
    token_with_sid = create_auth_token(repository.users["user-1"], settings, session_id="sess-1")
    request = _request_with_cookie(token_with_sid, path="/api/me")

    async def _raise_session_db_error(session_id: str):
        del session_id
        raise TimeoutError("database connection timeout")

    repository.get_session = _raise_session_db_error  # type: ignore[method-assign]
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.authenticate_request(request))

    assert exc_info.value.status_code == 503
    assert str(exc_info.value.detail) == "Auth database is temporarily unavailable. Please retry shortly."


def test_register_generates_uuid_user_id(tmp_path: Path) -> None:
    settings = _auth_settings(
        tmp_path / "users.json",
        database_enabled=False,
    )
    repository = FakeAuthRepository(settings, database_enabled=False, users=[])
    service = AuthService(settings=settings, repository=repository, notifier=_DummyNotifier())

    asyncio.run(
        service._store_verification_record(
            "register",
            "fresh@example.com",
            "123456",
        )
    )
    response = Response()
    result, status_code = asyncio.run(
        service.register(
            _request(path="/api/register"),
            response,
            {
                "name": "Fresh User",
                "email": "fresh@example.com",
                "phone": "13900000001",
                "password": "new-password-123",
                "code": "123456",
            },
        )
    )

    user_id = str(result["user"]["id"])
    assert status_code == 201
    assert len(user_id) == 32
    assert all(ch in "0123456789abcdef" for ch in user_id)
