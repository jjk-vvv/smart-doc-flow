from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.core.auth_config import AuthSettings

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ASYNCPG_MODULE: Any | None = None


def _load_asyncpg() -> Any:
    global _ASYNCPG_MODULE
    if _ASYNCPG_MODULE is None:
        import asyncpg as loaded_asyncpg

        _ASYNCPG_MODULE = loaded_asyncpg
    return _ASYNCPG_MODULE


def _retryable_connection_error_types() -> tuple[type[BaseException], ...]:
    try:
        asyncpg = _load_asyncpg()
    except Exception:
        return tuple()
    return tuple(
        error_type
        for error_type in (
            getattr(asyncpg, "InterfaceError", None),
            getattr(asyncpg, "PostgresConnectionError", None),
            getattr(asyncpg, "CannotConnectNowError", None),
            getattr(asyncpg, "ConnectionDoesNotExistError", None),
            getattr(asyncpg, "ConnectionFailureError", None),
        )
        if isinstance(error_type, type)
    )

INIT_SQL_TEMPLATE = """
CREATE SCHEMA IF NOT EXISTS {schema_name};

CREATE TABLE IF NOT EXISTS {schema_name}.users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS {users_email_idx}
ON {schema_name}.users (email)
WHERE email <> '';

CREATE UNIQUE INDEX IF NOT EXISTS {users_phone_idx}
ON {schema_name}.users (phone)
WHERE phone <> '';

CREATE TABLE IF NOT EXISTS {schema_name}.verification_codes (
    purpose TEXT NOT NULL,
    contact TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (purpose, contact)
);

CREATE INDEX IF NOT EXISTS {verification_expires_idx}
ON {schema_name}.verification_codes (expires_at);

CREATE TABLE IF NOT EXISTS {schema_name}.sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS {sessions_user_idx}
ON {schema_name}.sessions (user_id);

CREATE INDEX IF NOT EXISTS {sessions_expires_idx}
ON {schema_name}.sessions (expires_at);

CREATE TABLE IF NOT EXISTS {schema_name}.audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    ip_address TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS {audit_logs_event_idx}
ON {schema_name}.audit_logs (event_type, created_at DESC);
"""


def _quote_identifier(name: str) -> str:
    candidate = str(name or "").strip()
    if not IDENTIFIER_RE.fullmatch(candidate):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{candidate}"'


def _build_init_sql(schema_name: str) -> str:
    quoted_schema = _quote_identifier(schema_name)
    return INIT_SQL_TEMPLATE.format(
        schema_name=quoted_schema,
        users_email_idx=_quote_identifier(f"{schema_name}_users_email_uq"),
        users_phone_idx=_quote_identifier(f"{schema_name}_users_phone_uq"),
        verification_expires_idx=_quote_identifier(f"{schema_name}_verification_expires_idx"),
        sessions_user_idx=_quote_identifier(f"{schema_name}_sessions_user_idx"),
        sessions_expires_idx=_quote_identifier(f"{schema_name}_sessions_expires_idx"),
        audit_logs_event_idx=_quote_identifier(f"{schema_name}_audit_logs_event_idx"),
    )


def _rewrite_localhost_dsn(dsn: str, replacement_host: str = "127.0.0.1") -> str | None:
    raw = str(dsn or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except Exception:
        return None
    if not parts.scheme or not parts.hostname or parts.hostname.lower() != "localhost":
        return None

    auth = ""
    if parts.username is not None:
        auth = parts.username
        if parts.password is not None:
            auth = f"{auth}:{parts.password}"
        auth = f"{auth}@"
    host = replacement_host
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    rewritten = SplitResult(
        scheme=parts.scheme,
        netloc=f"{auth}{host}",
        path=parts.path,
        query=parts.query,
        fragment=parts.fragment,
    )
    return urlunsplit(rewritten)


def _redact_dsn(dsn: str) -> str:
    raw = str(dsn or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except Exception:
        return raw
    if not parts.scheme or not parts.hostname:
        return raw
    auth = ""
    if parts.username is not None:
        auth = parts.username
        if parts.password is not None:
            auth = f"{auth}:***"
        auth = f"{auth}@"
    host = parts.hostname
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    rewritten = SplitResult(
        scheme=parts.scheme,
        netloc=f"{auth}{host}",
        path=parts.path,
        query=parts.query,
        fragment=parts.fragment,
    )
    return urlunsplit(rewritten)


def _dsn_connection_candidates(dsn: str) -> list[str]:
    raw = str(dsn or "").strip()
    if not raw:
        return []
    fallback = _rewrite_localhost_dsn(raw)
    candidates = [raw]
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates


def _is_retryable_connection_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)):
        return True
    retryable_types = _retryable_connection_error_types()
    if retryable_types and isinstance(exc, retryable_types):
        return True
    return False


@dataclass(frozen=True)
class AuthDatabaseDiagnostics:
    enabled: bool
    connected: bool
    configured: bool
    dsn: str
    schema: str
    last_connect_error: str


class AuthDatabase:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings
        self._pool: Any | None = None
        self._connect_lock = asyncio.Lock()
        self._last_connect_error = ""
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.database_enabled and str(self.settings.database_dsn or "").strip())

    def diagnostics(self) -> AuthDatabaseDiagnostics:
        return AuthDatabaseDiagnostics(
            enabled=self.enabled,
            connected=self._pool is not None,
            configured=bool(str(self.settings.database_dsn or "").strip()),
            dsn=_redact_dsn(self.settings.database_dsn),
            schema=str(self.settings.database_schema or "").strip(),
            last_connect_error=self._last_connect_error,
        )

    async def ensure_ready(self) -> bool:
        if not self.enabled:
            return False
        current_loop = asyncio.get_running_loop()
        if self._pool is not None and self._loop is current_loop:
            return True
        if self._pool is not None and self._loop is not current_loop:
            self._discard_pool()
        async with self._connect_lock:
            if self._pool is not None and self._loop is current_loop:
                return True

            connect_errors: list[str] = []
            for candidate_dsn in _dsn_connection_candidates(self.settings.database_dsn):
                pool: Any | None = None
                try:
                    asyncpg = _load_asyncpg()
                    pool = await asyncio.wait_for(
                        asyncpg.create_pool(
                            candidate_dsn,
                            min_size=self.settings.db_pool_min_size,
                            max_size=max(self.settings.db_pool_min_size, self.settings.db_pool_max_size),
                            timeout=self.settings.db_connect_timeout_sec,
                        ),
                        timeout=max(self.settings.db_connect_timeout_sec + 1.0, 5.0),
                    )
                    async with pool.acquire() as connection:
                        await asyncio.wait_for(
                            connection.execute(_build_init_sql(self.settings.database_schema)),
                            timeout=max(self.settings.db_schema_timeout_sec, 5.0),
                        )
                    self._pool = pool
                    self._loop = current_loop
                    self._last_connect_error = ""
                    break
                except Exception as exc:
                    if pool is not None:
                        try:
                            await pool.close()
                        except Exception:
                            pass
                    connect_errors.append(f"{_redact_dsn(candidate_dsn)} -> {type(exc).__name__}: {exc}")

            if self._pool is None:
                self._last_connect_error = " | ".join(connect_errors) or "No valid auth database connection candidates"
                raise RuntimeError(self._last_connect_error)
        return True

    async def close(self) -> None:
        if self._pool is None:
            return
        pool = self._pool
        self._discard_pool()
        try:
            await pool.close()
        except Exception:
            return

    def _discard_pool(self) -> None:
        self._pool = None
        self._loop = None

    def mark_unavailable(self, exc: Exception | str | None = None) -> None:
        if exc is not None:
            self._last_connect_error = f"{type(exc).__name__}: {exc}" if isinstance(exc, Exception) else str(exc)
        self._discard_pool()

    async def _acquire_pool_connection(self) -> tuple[Any, Any]:
        last_exc: Exception | None = None
        for attempt_index in range(2):
            await self.ensure_ready()
            pool = self._pool
            if pool is None:
                raise RuntimeError("Auth database pool is not available")
            try:
                connection = await pool.acquire()
                self._last_connect_error = ""
                return pool, connection
            except Exception as exc:
                last_exc = exc
                self.mark_unavailable(exc)
                if attempt_index >= 1 or not _is_retryable_connection_error(exc):
                    raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Auth database pool is not available")

    @asynccontextmanager
    async def acquire(self):
        pool: Any | None = None
        connection: Any = None
        operation_error: Exception | None = None
        try:
            pool, connection = await self._acquire_pool_connection()
            yield connection
        except Exception as exc:
            operation_error = exc
            if connection is None or _is_retryable_connection_error(exc):
                self.mark_unavailable(exc)
            raise
        finally:
            if pool is not None and connection is not None:
                try:
                    await pool.release(connection)
                except Exception as exc:
                    self.mark_unavailable(exc)
                    if operation_error is None:
                        raise
