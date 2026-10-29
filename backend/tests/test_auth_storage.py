from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.auth_config import AuthSettings
from app.repositories.auth_storage import AuthDatabase


def _auth_settings(tmp_path: Path) -> AuthSettings:
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
        login_failure_window_ms=900000,
        login_max_failures_per_account=5,
        login_max_failures_per_ip=20,
        login_lock_ms=900000,
        is_prod=False,
        users_file=tmp_path / "users.json",
        smtp_host="",
        smtp_port=587,
        smtp_secure=False,
        smtp_user="",
        smtp_pass="",
        smtp_from="",
        database_enabled=True,
        database_dsn="postgresql://postgres@127.0.0.1:5433/Auth",
        database_schema="auth",
        db_connect_timeout_sec=3.0,
        db_schema_timeout_sec=8.0,
        db_pool_min_size=1,
        db_pool_max_size=10,
    )


class _FakePool:
    def __init__(self, *, connection: str = "conn", acquire_error: Exception | None = None) -> None:
        self.connection = connection
        self.acquire_error = acquire_error
        self.acquire_calls = 0
        self.release_calls: list[str] = []

    async def acquire(self):
        self.acquire_calls += 1
        if self.acquire_error is not None:
            raise self.acquire_error
        return self.connection

    async def release(self, connection) -> None:
        self.release_calls.append(str(connection))


def test_auth_database_retries_once_when_pool_acquire_times_out(tmp_path: Path) -> None:
    settings = _auth_settings(tmp_path)
    storage = AuthDatabase(settings)
    first_pool = _FakePool(acquire_error=TimeoutError("connect timed out"))
    second_pool = _FakePool(connection="conn-2")
    pool_sequence = [first_pool, second_pool]

    async def fake_ensure_ready() -> bool:
        if storage._pool is None:
            storage._pool = pool_sequence.pop(0)  # type: ignore[assignment]
            storage._loop = asyncio.get_running_loop()
        return True

    storage.ensure_ready = fake_ensure_ready  # type: ignore[method-assign]

    async def exercise() -> str:
        async with storage.acquire() as connection:
            return str(connection)

    result = asyncio.run(exercise())

    assert result == "conn-2"
    assert first_pool.acquire_calls == 1
    assert second_pool.acquire_calls == 1
    assert second_pool.release_calls == ["conn-2"]
    assert storage.diagnostics().last_connect_error == ""


def test_auth_database_does_not_retry_non_connection_errors(tmp_path: Path) -> None:
    settings = _auth_settings(tmp_path)
    storage = AuthDatabase(settings)
    failing_pool = _FakePool(acquire_error=ValueError("boom"))

    async def fake_ensure_ready() -> bool:
        if storage._pool is None:
            storage._pool = failing_pool  # type: ignore[assignment]
            storage._loop = asyncio.get_running_loop()
        return True

    storage.ensure_ready = fake_ensure_ready  # type: ignore[method-assign]

    async def exercise() -> None:
        async with storage.acquire():
            return None

    with pytest.raises(ValueError, match="boom"):
        asyncio.run(exercise())

    assert failing_pool.acquire_calls == 1
