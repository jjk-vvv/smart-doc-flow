from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.modules.auth.config import AuthSettings
from app.modules.auth.repository import AuthUserRepository


def _auth_settings(users_file: Path, legacy_users_file: Path) -> AuthSettings:
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
        users_file=users_file,
        legacy_users_file=legacy_users_file,
        sms_provider="",
        ihuyi_api_id="",
        ihuyi_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_secure=False,
        smtp_user="",
        smtp_pass="",
        smtp_from="",
        database_enabled=False,
        database_dsn="",
        database_schema="auth",
        db_connect_timeout_sec=3.0,
        db_schema_timeout_sec=8.0,
        db_pool_min_size=1,
        db_pool_max_size=10,
    )


def test_auth_repository_migrates_legacy_users_into_managed_storage(tmp_path: Path) -> None:
    legacy_users_file = tmp_path / "backend" / "auth" / "users.json"
    legacy_users_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_users_file.write_text(
        json.dumps(
            [
                {
                    "id": "u1",
                    "name": "legacy-user",
                    "email": "legacy@example.com",
                    "phone": "13800138000",
                    "password": "plaintext",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    managed_users_file = tmp_path / "managed-data" / "auth" / "users.json"

    repository = AuthUserRepository(_auth_settings(managed_users_file, legacy_users_file))

    state = repository.resolve_storage_state()
    loaded_users = asyncio.run(repository.load_users())
    follow_up_state = repository.resolve_storage_state()

    assert state.mode == "migrated_from_legacy"
    assert state.migrated_from_legacy is True
    assert managed_users_file.exists() is True
    assert loaded_users[0]["email"] == "legacy@example.com"
    assert follow_up_state.mode == "managed"
    assert follow_up_state.active_path == managed_users_file.resolve()


def test_auth_settings_can_fallback_to_module4_database_dsn(tmp_path: Path, monkeypatch) -> None:
    module4_env = tmp_path / "backend" / "module4" / ".env"
    module4_env.parent.mkdir(parents=True, exist_ok=True)
    module4_env.write_text(
        "MODULE4_DATABASE_DSN=postgresql://postgres:postgres@127.0.0.1:5433/Knowledge_Graph\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("AUTH_DATABASE_DSN", raising=False)
    monkeypatch.delenv("AUTH_DATABASE_ENABLED", raising=False)
    monkeypatch.setenv("SMART_DOC_FLOW_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.delenv("SMART_DOC_FLOW_CONFIG_ROOT", raising=False)
    monkeypatch.delenv("SMART_DOC_FLOW_DATA_ROOT", raising=False)

    settings = AuthSettings.from_env()

    assert settings.database_enabled is True
    assert settings.database_dsn == "postgresql://postgres:postgres@127.0.0.1:5433/Knowledge_Graph"
    assert settings.database_schema == "auth"
