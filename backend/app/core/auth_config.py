from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import resolve_config_root_dir, resolve_runtime_root_dir


def _env_str(name: str, default: str = "") -> str:
    value = str(os.getenv(name, default) or "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.getenv(name, default) or "").strip()
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw_value = str(os.getenv(name, "") or "").strip().lower()
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _parse_env_file_value(file_path: Path, key: str) -> str:
    if not file_path.exists() or not file_path.is_file():
        return ""
    for raw_line in file_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = str(raw_line or "").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, current_value = line.split("=", 1)
        if current_key.strip() != key:
            continue
        value = current_value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value
    return ""


def _resolve_fallback_database_dsn(runtime_root: Path) -> str:
    config_root = resolve_config_root_dir(runtime_root)
    candidates = (
        (config_root / "backend" / "module4" / ".env").resolve(),
        (runtime_root / "backend" / "module4" / ".env").resolve(),
    )
    for candidate in candidates:
        value = _parse_env_file_value(candidate, "MODULE4_DATABASE_DSN")
        if value:
            return value
    return ""


@dataclass(frozen=True)
class AuthSettings:
    secret_key: str
    token_expires_in: str
    cookie_name: str
    cookie_max_age_days: int
    password_salt_rounds: int
    verify_code_expires_ms: int
    send_code_window_ms: int
    send_code_max_per_contact: int
    send_code_max_per_ip: int
    send_code_cooldown_ms: int
    login_failure_window_ms: int
    login_max_failures_per_account: int
    login_max_failures_per_ip: int
    login_lock_ms: int
    is_prod: bool
    users_file: Path
    sms_provider: str
    ihuyi_api_id: str
    ihuyi_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_secure: bool
    smtp_user: str
    smtp_pass: str
    smtp_from: str
    database_enabled: bool
    database_dsn: str
    database_schema: str
    db_connect_timeout_sec: float
    db_schema_timeout_sec: float
    db_pool_min_size: int
    db_pool_max_size: int
    require_session_id_in_db_mode: bool = True
    enforce_secret_key_in_production: bool = True
    secret_key_min_length: int = 32

    @classmethod
    def from_env(cls) -> "AuthSettings":
        runtime_root = resolve_runtime_root_dir()
        configured_secret = _env_str("AUTH_SECRET_KEY", "")
        is_prod = _env_str("NODE_ENV", "development").lower() == "production"
        enforce_secret_key_in_production = _env_bool("AUTH_ENFORCE_SECRET_KEY_IN_PRODUCTION", True)
        secret_key_min_length = max(16, _env_int("AUTH_SECRET_KEY_MIN_LENGTH", 32))
        if is_prod and enforce_secret_key_in_production:
            if not configured_secret:
                raise RuntimeError("AUTH_SECRET_KEY is required in production mode")
            if len(configured_secret) < secret_key_min_length:
                raise RuntimeError(
                    f"AUTH_SECRET_KEY must be at least {secret_key_min_length} characters in production mode"
                )
        configured_database_dsn = _env_str("AUTH_DATABASE_DSN", "") or _resolve_fallback_database_dsn(runtime_root)
        return cls(
            secret_key=configured_secret or secrets.token_hex(32),
            token_expires_in=_env_str("AUTH_TOKEN_EXPIRES_IN", "7d"),
            cookie_name=_env_str("AUTH_COOKIE_NAME", "token"),
            cookie_max_age_days=max(1, _env_int("AUTH_COOKIE_MAX_AGE_DAYS", 7)),
            password_salt_rounds=max(4, _env_int("AUTH_PASSWORD_SALT_ROUNDS", 10)),
            verify_code_expires_ms=max(
                60 * 1000,
                _env_int("AUTH_VERIFY_CODE_EXPIRES_MS", 5 * 60 * 1000),
            ),
            send_code_window_ms=max(
                60 * 1000,
                _env_int("AUTH_SEND_CODE_WINDOW_MS", 10 * 60 * 1000),
            ),
            send_code_max_per_contact=max(1, _env_int("AUTH_SEND_CODE_MAX_PER_CONTACT", 5)),
            send_code_max_per_ip=max(1, _env_int("AUTH_SEND_CODE_MAX_PER_IP", 20)),
            send_code_cooldown_ms=max(
                10 * 1000,
                _env_int("AUTH_SEND_CODE_COOLDOWN_MS", 60 * 1000),
            ),
            login_failure_window_ms=max(
                60 * 1000,
                _env_int("AUTH_LOGIN_FAILURE_WINDOW_MS", 15 * 60 * 1000),
            ),
            login_max_failures_per_account=max(
                1,
                _env_int("AUTH_LOGIN_MAX_FAILURES_PER_ACCOUNT", 5),
            ),
            login_max_failures_per_ip=max(
                1,
                _env_int("AUTH_LOGIN_MAX_FAILURES_PER_IP", 20),
            ),
            login_lock_ms=max(
                30 * 1000,
                _env_int("AUTH_LOGIN_LOCK_MS", 15 * 60 * 1000),
            ),
            is_prod=is_prod,
            users_file=Path(
                _env_str(
                    "AUTH_USERS_FILE",
                    str(runtime_root / "auth" / "users.json"),
                )
            ).expanduser().resolve(),
            sms_provider=_env_str("AUTH_SMS_PROVIDER", "").lower(),
            ihuyi_api_id=_env_str("AUTH_IHUYI_API_ID", ""),
            ihuyi_api_key=_env_str("AUTH_IHUYI_API_KEY", ""),
            smtp_host=_env_str("AUTH_SMTP_HOST", ""),
            smtp_port=max(1, _env_int("AUTH_SMTP_PORT", 587)),
            smtp_secure=_env_str("AUTH_SMTP_SECURE", "").lower() == "true",
            smtp_user=_env_str("AUTH_SMTP_USER", ""),
            smtp_pass=_env_str("AUTH_SMTP_PASS", ""),
            smtp_from=_env_str("AUTH_SMTP_FROM", ""),
            database_enabled=_env_bool("AUTH_DATABASE_ENABLED", bool(configured_database_dsn)),
            database_dsn=configured_database_dsn,
            database_schema=_env_str("AUTH_DATABASE_SCHEMA", "auth"),
            db_connect_timeout_sec=max(1.0, _env_float("AUTH_DB_CONNECT_TIMEOUT_SEC", 3.0)),
            db_schema_timeout_sec=max(1.0, _env_float("AUTH_DB_SCHEMA_TIMEOUT_SEC", 8.0)),
            db_pool_min_size=max(1, _env_int("AUTH_DB_POOL_MIN_SIZE", 1)),
            db_pool_max_size=max(1, _env_int("AUTH_DB_POOL_MAX_SIZE", 10)),
            require_session_id_in_db_mode=_env_bool("AUTH_REQUIRE_SESSION_ID_IN_DB_MODE", True),
            enforce_secret_key_in_production=enforce_secret_key_in_production,
            secret_key_min_length=secret_key_min_length,
        )
