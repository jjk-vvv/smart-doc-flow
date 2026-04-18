from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.auth_config import AuthSettings
from app.core.auth_security import normalize_str
from app.repositories.auth_storage import AuthDatabase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_execute_rowcount(result: str) -> int:
    raw = str(result or "").strip()
    if not raw:
        return 0
    parts = raw.split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except (TypeError, ValueError):
        return 0


def _normalize_user_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": normalize_str(item.get("id")),
        "name": normalize_str(item.get("name")),
        "email": normalize_str(item.get("email")),
        "phone": normalize_str(item.get("phone")),
        "password": normalize_str(item.get("password")),
        "status": normalize_str(item.get("status")) or "active",
        "last_login_at": item.get("last_login_at"),
    }


@dataclass(frozen=True)
class AuthStorageState:
    active_path: Path
    preferred_path: Path
    mode: str


class AuthUserRepository:
    def __init__(self, settings: AuthSettings) -> None:
        self.settings = settings
        self.storage = AuthDatabase(settings)
        self._lock = threading.RLock()
        self._migration_lock = threading.RLock()
        self._database_seed_completed = False

    @property
    def database_enabled(self) -> bool:
        return self.storage.enabled

    def resolve_storage_state(self) -> AuthStorageState:
        preferred = self.settings.users_file
        preferred.parent.mkdir(parents=True, exist_ok=True)
        return AuthStorageState(
            active_path=preferred,
            preferred_path=preferred,
            mode="managed",
        )

    async def ensure_ready(self) -> bool:
        if not self.database_enabled:
            return False
        await self.storage.ensure_ready()
        await self._migrate_file_users_to_database_if_needed()
        return True

    async def shutdown(self) -> None:
        await self.storage.close()

    async def count_users(self) -> int:
        if not self.database_enabled:
            return len(self._load_users_from_file())
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            value = await connection.fetchval(
                f'SELECT COUNT(1) FROM "{self.settings.database_schema}".users'
            )
        return int(value or 0)

    async def load_users(self) -> list[dict[str, Any]]:
        if not self.database_enabled:
            return self._load_users_from_file()
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            rows = await connection.fetch(
                f'''
                SELECT id, name, email, phone, password, status, last_login_at
                FROM "{self.settings.database_schema}".users
                ORDER BY created_at ASC, id ASC
                '''
            )
        return [_normalize_user_record(dict(row)) for row in rows]

    async def find_user_by_account(self, account: str) -> dict[str, Any] | None:
        normalized_account = normalize_str(account)
        if not normalized_account:
            return None
        if not self.database_enabled:
            return next(
                (
                    item
                    for item in self._load_users_from_file()
                    if item["email"] == normalized_account
                    or item["phone"] == normalized_account
                    or item["name"] == normalized_account
                ),
                None,
            )
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT id, name, email, phone, password, status, last_login_at
                FROM "{self.settings.database_schema}".users
                WHERE email = $1 OR phone = $1 OR name = $1
                LIMIT 1
                ''',
                normalized_account,
            )
        return _normalize_user_record(dict(row)) if row else None

    async def find_user_by_contact(self, contact: str) -> dict[str, Any] | None:
        normalized_contact = normalize_str(contact)
        if not normalized_contact:
            return None
        if not self.database_enabled:
            return next(
                (
                    item
                    for item in self._load_users_from_file()
                    if item["email"] == normalized_contact or item["phone"] == normalized_contact
                ),
                None,
            )
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT id, name, email, phone, password, status, last_login_at
                FROM "{self.settings.database_schema}".users
                WHERE email = $1 OR phone = $1
                LIMIT 1
                ''',
                normalized_contact,
            )
        return _normalize_user_record(dict(row)) if row else None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        normalized_user_id = normalize_str(user_id)
        if not normalized_user_id:
            return None
        if not self.database_enabled:
            return next(
                (item for item in self._load_users_from_file() if item["id"] == normalized_user_id),
                None,
            )
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT id, name, email, phone, password, status, last_login_at
                FROM "{self.settings.database_schema}".users
                WHERE id = $1
                LIMIT 1
                ''',
                normalized_user_id,
            )
        return _normalize_user_record(dict(row)) if row else None

    async def find_existing_identity(self, name: str, email: str, phone: str) -> dict[str, Any] | None:
        normalized_name = normalize_str(name)
        normalized_email = normalize_str(email)
        normalized_phone = normalize_str(phone)
        if not self.database_enabled:
            return next(
                (
                    item
                    for item in self._load_users_from_file()
                    if item["name"] == normalized_name
                    or item["email"] == normalized_email
                    or item["phone"] == normalized_phone
                ),
                None,
            )
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT id, name, email, phone, password, status, last_login_at
                FROM "{self.settings.database_schema}".users
                WHERE name = $1 OR email = $2 OR phone = $3
                LIMIT 1
                ''',
                normalized_name,
                normalized_email,
                normalized_phone,
            )
        return _normalize_user_record(dict(row)) if row else None

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        normalized_user = _normalize_user_record(user)
        if not self.database_enabled:
            users = self._load_users_from_file()
            users.append(normalized_user)
            self._save_users_to_file(users)
            return normalized_user
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                INSERT INTO "{self.settings.database_schema}".users
                    (id, name, email, phone, password, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                ''',
                normalized_user["id"],
                normalized_user["name"],
                normalized_user["email"],
                normalized_user["phone"],
                normalized_user["password"],
                normalized_user["status"],
            )
        return normalized_user

    async def update_user_password(self, user_id: str, password_hash: str) -> None:
        normalized_user_id = normalize_str(user_id)
        normalized_password_hash = normalize_str(password_hash)
        if not self.database_enabled:
            users = self._load_users_from_file()
            for user in users:
                if user["id"] != normalized_user_id:
                    continue
                user["password"] = normalized_password_hash
                break
            self._save_users_to_file(users)
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".users
                SET password = $2, updated_at = NOW()
                WHERE id = $1
                ''',
                normalized_user_id,
                normalized_password_hash,
            )

    async def touch_last_login(self, user_id: str) -> None:
        normalized_user_id = normalize_str(user_id)
        if not normalized_user_id:
            return
        if not self.database_enabled:
            users = self._load_users_from_file()
            for user in users:
                if user["id"] != normalized_user_id:
                    continue
                user["last_login_at"] = _utc_now().isoformat()
                break
            self._save_users_to_file(users)
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".users
                SET last_login_at = NOW(), updated_at = NOW()
                WHERE id = $1
                ''',
                normalized_user_id,
            )

    async def store_verification_code(
        self,
        *,
        purpose: str,
        contact: str,
        code_hash: str,
        expires_at: datetime,
        user_id: str = "",
    ) -> None:
        if not self.database_enabled:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                INSERT INTO "{self.settings.database_schema}".verification_codes
                    (purpose, contact, code_hash, user_id, expires_at, consumed_at, created_at)
                VALUES ($1, $2, $3, $4, $5, NULL, NOW())
                ON CONFLICT (purpose, contact)
                DO UPDATE SET
                    code_hash = EXCLUDED.code_hash,
                    user_id = EXCLUDED.user_id,
                    expires_at = EXCLUDED.expires_at,
                    consumed_at = NULL,
                    created_at = NOW()
                ''',
                normalize_str(purpose),
                normalize_str(contact),
                normalize_str(code_hash),
                normalize_str(user_id),
                expires_at,
            )

    async def get_verification_code(self, *, purpose: str, contact: str) -> dict[str, Any] | None:
        if not self.database_enabled:
            return None
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT purpose, contact, code_hash, user_id, expires_at, consumed_at, created_at
                FROM "{self.settings.database_schema}".verification_codes
                WHERE purpose = $1 AND contact = $2 AND consumed_at IS NULL
                LIMIT 1
                ''',
                normalize_str(purpose),
                normalize_str(contact),
            )
        return dict(row) if row else None

    async def delete_verification_code(self, *, purpose: str, contact: str) -> None:
        if not self.database_enabled:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                DELETE FROM "{self.settings.database_schema}".verification_codes
                WHERE purpose = $1 AND contact = $2
                ''',
                normalize_str(purpose),
                normalize_str(contact),
            )

    async def create_session(
        self,
        *,
        session_id: str,
        user_id: str,
        expires_at: datetime,
        ip_address: str,
        user_agent: str,
    ) -> None:
        if not self.database_enabled:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                INSERT INTO "{self.settings.database_schema}".sessions
                    (session_id, user_id, ip_address, user_agent, expires_at)
                VALUES ($1, $2, $3, $4, $5)
                ''',
                normalize_str(session_id),
                normalize_str(user_id),
                normalize_str(ip_address),
                normalize_str(user_agent),
                expires_at,
            )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        if not self.database_enabled:
            return None
        normalized_session_id = normalize_str(session_id)
        if not normalized_session_id:
            return None
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            row = await connection.fetchrow(
                f'''
                SELECT session_id, user_id, ip_address, user_agent, created_at, last_seen_at, expires_at, revoked_at
                FROM "{self.settings.database_schema}".sessions
                WHERE session_id = $1
                LIMIT 1
                ''',
                normalized_session_id,
            )
        return dict(row) if row else None

    async def list_sessions_for_user(self, user_id: str) -> list[dict[str, Any]]:
        if not self.database_enabled:
            return []
        normalized_user_id = normalize_str(user_id)
        if not normalized_user_id:
            return []
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            rows = await connection.fetch(
                f'''
                SELECT session_id, user_id, ip_address, user_agent, created_at, last_seen_at, expires_at, revoked_at
                FROM "{self.settings.database_schema}".sessions
                WHERE user_id = $1
                ORDER BY created_at DESC, session_id DESC
                ''',
                normalized_user_id,
            )
        return [dict(row) for row in rows]

    async def touch_session(self, session_id: str) -> None:
        if not self.database_enabled:
            return
        normalized_session_id = normalize_str(session_id)
        if not normalized_session_id:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".sessions
                SET last_seen_at = NOW()
                WHERE session_id = $1
                ''',
                normalized_session_id,
            )

    async def revoke_session(self, session_id: str) -> None:
        if not self.database_enabled:
            return
        normalized_session_id = normalize_str(session_id)
        if not normalized_session_id:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".sessions
                SET revoked_at = NOW()
                WHERE session_id = $1
                ''',
                normalized_session_id,
            )

    async def revoke_session_for_user(self, user_id: str, session_id: str) -> bool:
        if not self.database_enabled:
            return False
        normalized_user_id = normalize_str(user_id)
        normalized_session_id = normalize_str(session_id)
        if not normalized_user_id or not normalized_session_id:
            return False
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            result = await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".sessions
                SET revoked_at = COALESCE(revoked_at, NOW())
                WHERE user_id = $1 AND session_id = $2
                ''',
                normalized_user_id,
                normalized_session_id,
            )
        return _parse_execute_rowcount(result) > 0

    async def revoke_sessions_for_user(self, user_id: str) -> None:
        if not self.database_enabled:
            return
        normalized_user_id = normalize_str(user_id)
        if not normalized_user_id:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                UPDATE "{self.settings.database_schema}".sessions
                SET revoked_at = COALESCE(revoked_at, NOW())
                WHERE user_id = $1 AND revoked_at IS NULL
                ''',
                normalized_user_id,
            )

    async def revoke_other_sessions_for_user(self, user_id: str, *, exclude_session_id: str = "") -> int:
        if not self.database_enabled:
            return 0
        normalized_user_id = normalize_str(user_id)
        normalized_exclude_session_id = normalize_str(exclude_session_id)
        if not normalized_user_id:
            return 0
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            if normalized_exclude_session_id:
                result = await connection.execute(
                    f'''
                    UPDATE "{self.settings.database_schema}".sessions
                    SET revoked_at = COALESCE(revoked_at, NOW())
                    WHERE user_id = $1 AND session_id <> $2 AND revoked_at IS NULL
                    ''',
                    normalized_user_id,
                    normalized_exclude_session_id,
                )
            else:
                result = await connection.execute(
                    f'''
                    UPDATE "{self.settings.database_schema}".sessions
                    SET revoked_at = COALESCE(revoked_at, NOW())
                    WHERE user_id = $1 AND revoked_at IS NULL
                    ''',
                    normalized_user_id,
                )
        return _parse_execute_rowcount(result)

    async def append_audit_log(
        self,
        *,
        event_type: str,
        user_id: str = "",
        ip_address: str = "",
        user_agent: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if not self.database_enabled:
            return
        await self.ensure_ready()
        async with self.storage.acquire() as connection:
            await connection.execute(
                f'''
                INSERT INTO "{self.settings.database_schema}".audit_logs
                    (user_id, event_type, ip_address, user_agent, payload)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ''',
                normalize_str(user_id),
                normalize_str(event_type),
                normalize_str(ip_address),
                normalize_str(user_agent),
                json.dumps(payload or {}, ensure_ascii=False),
            )

    def _load_users_from_file(self) -> list[dict[str, Any]]:
        storage_path = self.resolve_storage_path()
        return self._read_users_from_path(storage_path)

    def resolve_storage_path(self) -> Path:
        return self.resolve_storage_state().active_path

    def _read_users_from_path(self, storage_path: Path) -> list[dict[str, Any]]:
        if not storage_path.exists():
            return []
        try:
            raw_text = storage_path.read_text(encoding="utf-8")
            parsed = json.loads(raw_text)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(parsed, list):
            return []
        users: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            users.append(_normalize_user_record(item))
        return users

    def _save_users_to_file(self, users: list[dict[str, Any]]) -> None:
        storage_path = self.resolve_storage_path()
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            storage_path.write_text(
                json.dumps(users, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    async def _migrate_file_users_to_database_if_needed(self) -> None:
        if not self.database_enabled or self._database_seed_completed:
            return
        with self._migration_lock:
            if self._database_seed_completed:
                return

        file_users = self._load_users_from_file()
        if not file_users:
            with self._migration_lock:
                self._database_seed_completed = True
            return

        async with self.storage.acquire() as connection:
            async with connection.transaction():
                existing_count = await connection.fetchval(
                    f'SELECT COUNT(1) FROM "{self.settings.database_schema}".users'
                )
                if int(existing_count or 0) == 0:
                    for user in file_users:
                        normalized_user = _normalize_user_record(user)
                        await connection.execute(
                            f'''
                            INSERT INTO "{self.settings.database_schema}".users
                                (id, name, email, phone, password, status)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (id)
                            DO UPDATE SET
                                name = EXCLUDED.name,
                                email = EXCLUDED.email,
                                phone = EXCLUDED.phone,
                                password = EXCLUDED.password,
                                status = EXCLUDED.status,
                                updated_at = NOW()
                            ''',
                            normalized_user["id"],
                            normalized_user["name"],
                            normalized_user["email"],
                            normalized_user["phone"],
                            normalized_user["password"],
                            normalized_user["status"],
                        )

        with self._migration_lock:
            self._database_seed_completed = True
