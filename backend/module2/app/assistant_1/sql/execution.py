from __future__ import annotations

from typing import Any

import asyncpg

from ..config import Assistant1Settings
from ..text_utils import normalize_text
from .common import READ_STATEMENTS, WRITE_STATEMENTS, detect_statement_type, is_single_statement, normalize_params


class Assistant1SqlExecutionService:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()

    def execute_sql_with_audit(
        self,
        *,
        sql: str,
        params: list[Any] | None = None,
        confirmed: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        import asyncio

        return asyncio.run(
            self._execute_sql_with_audit(
                sql=sql,
                params=params or [],
                confirmed=confirmed,
                reason=reason,
            )
        )

    async def _execute_sql_with_audit(
        self,
        *,
        sql: str,
        params: list[Any],
        confirmed: bool,
        reason: str,
    ) -> dict[str, Any]:
        sql_text = str(sql or "").strip()
        if not sql_text:
            return {"ok": False, "error": "sql is required"}
        if not is_single_statement(sql_text):
            return {"ok": False, "error": "only a single SQL statement is allowed"}
        statement_type = detect_statement_type(sql_text)
        if not statement_type:
            return {"ok": False, "error": "unable to detect SQL statement type"}
        if statement_type in WRITE_STATEMENTS and not confirmed:
            return {
                "ok": False,
                "error": "write or DDL statements require confirmed=true",
                "statement_type": statement_type,
            }

        conn = await asyncpg.connect(dsn=self.settings.database_dsn, timeout=self.settings.sql_timeout_sec)
        success = False
        row_count = 0
        result_preview: list[dict[str, Any]] = []
        error_text = ""
        try:
            await self._ensure_audit_schema(conn)
            async with conn.transaction():
                await conn.execute(f"SET LOCAL statement_timeout = '{int(self.settings.sql_timeout_sec * 1000)}ms'")
                normalized_params = normalize_params(params)
                if statement_type in READ_STATEMENTS:
                    rows = await conn.fetch(sql_text, *normalized_params)
                    row_count = len(rows)
                    result_preview = [
                        self._json_ready_row(dict(row))
                        for row in rows[: self.settings.sql_max_preview_rows]
                    ]
                else:
                    status = await conn.execute(sql_text, *normalized_params)
                    row_count = self._extract_row_count(status)
                    result_preview = [{"status": status}]
                success = True
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
        audit_id = await self._record_audit(
            conn,
            sql_text=sql_text,
            params=params,
            statement_type=statement_type,
            confirmed=confirmed,
            reason=reason,
            success=success,
            row_count=row_count,
            error_text=error_text,
            result_preview=result_preview,
        )
        await conn.close()

        if not success:
            return {
                "ok": False,
                "statement_type": statement_type,
                "audit_id": audit_id,
                "error": error_text or "SQL execution failed",
            }
        return {
            "ok": True,
            "statement_type": statement_type,
            "audit_id": audit_id,
            "row_count": row_count,
            "result_preview": result_preview,
            "confirmed": confirmed,
        }

    async def _ensure_audit_schema(self, conn: asyncpg.Connection) -> None:
        await conn.execute(
            """
            CREATE EXTENSION IF NOT EXISTS pgcrypto;
            CREATE TABLE IF NOT EXISTS doc_sql_audit (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at timestamptz NOT NULL DEFAULT NOW(),
                source text NOT NULL DEFAULT 'assistant_1',
                statement_type text NOT NULL,
                sql_text text NOT NULL,
                params_json jsonb NOT NULL DEFAULT '[]'::jsonb,
                confirmed boolean NOT NULL DEFAULT false,
                success boolean NOT NULL,
                row_count integer NOT NULL DEFAULT 0,
                reason text,
                error_text text,
                result_preview_json jsonb NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )

    async def _record_audit(
        self,
        conn: asyncpg.Connection,
        *,
        sql_text: str,
        params: list[Any],
        statement_type: str,
        confirmed: bool,
        reason: str,
        success: bool,
        row_count: int,
        error_text: str,
        result_preview: list[dict[str, Any]],
    ) -> str:
        import json

        row = await conn.fetchrow(
            """
            INSERT INTO doc_sql_audit (
                statement_type,
                sql_text,
                params_json,
                confirmed,
                success,
                row_count,
                reason,
                error_text,
                result_preview_json
            )
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9::jsonb)
            RETURNING id
            """,
            statement_type,
            sql_text,
            json.dumps(params, ensure_ascii=False),
            confirmed,
            success,
            row_count,
            normalize_text(reason),
            error_text,
            json.dumps(result_preview, ensure_ascii=False),
        )
        return str(row["id"])

    @staticmethod
    def _json_ready_row(row: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        return cleaned

    @staticmethod
    def _extract_row_count(status: str) -> int:
        parts = str(status or "").split()
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
        return 0
