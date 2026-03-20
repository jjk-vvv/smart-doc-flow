from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import asyncpg

from .config import Assistant1Settings
from .responses_provider import Assistant1ResponsesProvider
from .text_utils import normalize_text


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL | re.IGNORECASE)
_WRITE_STATEMENTS = {"insert", "update", "delete", "merge", "alter", "drop", "create", "truncate", "grant", "revoke"}
_READ_STATEMENTS = {"select", "with", "show", "explain"}


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty response")
    match = _JSON_BLOCK_RE.search(raw)
    candidate = match.group(1) if match else raw
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end >= start:
        candidate = candidate[start : end + 1]
    loaded = json.loads(candidate)
    if not isinstance(loaded, dict):
        raise ValueError("response is not a JSON object")
    return loaded


def _quote_ident(name: str) -> str:
    cleaned = str(name or "").strip().replace('"', "")
    if not cleaned:
        raise ValueError("identifier is required")
    return f'"{cleaned}"'


def _detect_statement_type(sql: str) -> str:
    text = str(sql or "").strip().lstrip("(").strip()
    if not text:
        return ""
    first = re.split(r"\s+", text, maxsplit=1)[0].lower()
    return first


def _is_single_statement(sql: str) -> bool:
    text = str(sql or "").strip()
    if not text:
        return False
    body = text.rstrip().rstrip(";")
    return ";" not in body


def _normalize_params(params: Any) -> list[Any]:
    if params is None:
        return []
    if isinstance(params, list):
        return params
    return [params]


class Assistant1SqlTools:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        provider: Assistant1ResponsesProvider | None = None,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = provider or Assistant1ResponsesProvider(self.settings)

    def inspect_database_schema(
        self,
        *,
        schemas: list[str] | None = None,
        table_names: list[str] | None = None,
        include_columns: bool = True,
    ) -> dict[str, Any]:
        return asyncio.run(
            self._inspect_database_schema(
                schemas=schemas or [],
                table_names=table_names or [],
                include_columns=include_columns,
            )
        )

    async def _inspect_database_schema(
        self,
        *,
        schemas: list[str],
        table_names: list[str],
        include_columns: bool,
    ) -> dict[str, Any]:
        conn = await asyncpg.connect(dsn=self.settings.database_dsn, timeout=self.settings.sql_timeout_sec)
        try:
            safe_schemas = [normalize_text(item) for item in schemas if normalize_text(item)]
            safe_tables = [normalize_text(item) for item in table_names if normalize_text(item)]
            table_filters: list[str] = ["table_schema NOT IN ('pg_catalog', 'information_schema')"]
            params: list[Any] = []
            schema_param_index = 0
            table_param_index = 0
            if safe_schemas:
                params.append(safe_schemas)
                schema_param_index = len(params)
                table_filters.append(f"table_schema = ANY(${len(params)}::text[])")
            if safe_tables:
                params.append(safe_tables)
                table_param_index = len(params)
                table_filters.append(f"table_name = ANY(${len(params)}::text[])")
            where_clause = " AND ".join(table_filters)
            tc_filters: list[str] = ["tc.table_schema NOT IN ('pg_catalog', 'information_schema')"]
            if safe_schemas:
                tc_filters.append(f"tc.table_schema = ANY(${schema_param_index}::text[])")
            if safe_tables:
                tc_filters.append(f"tc.table_name = ANY(${table_param_index}::text[])")
            tc_where_clause = " AND ".join(tc_filters)
            tables = await conn.fetch(
                f"""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE {where_clause}
                  AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
                """,
                *params,
            )
            table_map: dict[tuple[str, str], dict[str, Any]] = {}
            for row in tables:
                key = (row["table_schema"], row["table_name"])
                table_map[key] = {
                    "schema": row["table_schema"],
                    "table_name": row["table_name"],
                    "columns": [],
                    "primary_key": [],
                    "indexes": [],
                }

            if include_columns and table_map:
                column_rows = await conn.fetch(
                    f"""
                    SELECT table_schema, table_name, column_name, data_type, udt_name, is_nullable, column_default, ordinal_position
                    FROM information_schema.columns
                    WHERE {where_clause}
                    ORDER BY table_schema, table_name, ordinal_position
                    """,
                    *params,
                )
                for row in column_rows:
                    key = (row["table_schema"], row["table_name"])
                    if key not in table_map:
                        continue
                    table_map[key]["columns"].append(
                        {
                            "name": row["column_name"],
                            "data_type": row["data_type"],
                            "udt_name": row["udt_name"],
                            "nullable": row["is_nullable"] == "YES",
                            "default": row["column_default"],
                        }
                    )

            if table_map:
                pk_rows = await conn.fetch(
                    f"""
                    SELECT tc.table_schema, tc.table_name, kcu.column_name, kcu.ordinal_position
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                     AND tc.table_name = kcu.table_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND {tc_where_clause}
                    ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
                    """,
                    *params,
                )
                for row in pk_rows:
                    key = (row["table_schema"], row["table_name"])
                    if key in table_map:
                        table_map[key]["primary_key"].append(row["column_name"])

                index_rows = await conn.fetch(
                    f"""
                    SELECT schemaname, tablename, indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY schemaname, tablename, indexname
                    """
                )
                for row in index_rows:
                    key = (row["schemaname"], row["tablename"])
                    if key in table_map:
                        table_map[key]["indexes"].append(
                            {
                                "name": row["indexname"],
                                "definition": row["indexdef"],
                            }
                        )

            return {
                "ok": True,
                "table_count": len(table_map),
                "tables": list(table_map.values()),
            }
        finally:
            await conn.close()

    def draft_sql_from_nl(
        self,
        *,
        request: str,
        allowed_tables: list[str] | None = None,
        mode: str = "read_only",
    ) -> dict[str, Any]:
        question = normalize_text(request)
        if not question:
            return {"ok": False, "error": "request is required"}
        schema_snapshot = self.inspect_database_schema(table_names=allowed_tables or [], include_columns=True)
        if not schema_snapshot.get("ok"):
            return schema_snapshot
        if not self.provider.configured:
            return {"ok": False, "error": "chat provider is not configured for SQL drafting"}

        safe_mode = str(mode or "read_only").strip().lower()
        if safe_mode not in {"read_only", "read_write_draft"}:
            safe_mode = "read_only"

        schema_context = self._render_schema_context(schema_snapshot)
        prompt = (
            "根据下面的 PostgreSQL 数据库结构，把用户请求转换成 SQL 草案。\n"
            "只输出 JSON 对象，不要输出 markdown，不要输出解释性前后缀。\n"
            "JSON 键固定为：sql, statement_type, explanation, assumptions, tables, requires_confirmation。\n"
            "如果信息不足或请求和现有表结构不匹配，可以把 sql 设为空字符串，并在 explanation 里说明缺什么。\n"
            "如果用户在问数量、总数、多少条记录，优先使用 COUNT(*) 这类聚合 SQL。\n"
        )
        if safe_mode == "read_only":
            prompt += "本轮只允许生成只读 SQL（SELECT / WITH / EXPLAIN / SHOW），不要生成写操作。\n"
        else:
            prompt += "本轮可以生成写操作草案，但要明确是否需要确认。\n"
        prompt += f"\n数据库结构：\n{schema_context}\n\n用户请求：{question}"

        result = self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            instructions=(
                "你是 PostgreSQL SQL 设计助手。"
                "输出 JSON 对象即可。"
                "SQL 必须只使用给定表和列。"
            ),
            max_output_tokens=min(1600, self.settings.chat_max_output_tokens),
            reasoning_effort="minimal",
            text_verbosity="low",
            metadata={"assistant_runtime": "assistant_1", "phase": "draft_sql_from_nl"},
        )
        try:
            data = _extract_json_object(result.output_text)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"failed to parse SQL draft JSON: {type(exc).__name__}: {exc}",
                "raw_text": result.output_text,
            }

        sql_text = str(data.get("sql") or "").strip()
        statement_type = _detect_statement_type(sql_text) or str(data.get("statement_type") or "").strip().lower()
        requires_confirmation = bool(data.get("requires_confirmation"))
        if not sql_text:
            heuristic = self._heuristic_sql_draft(
                request=question,
                allowed_tables=allowed_tables or [],
                schema_snapshot=schema_snapshot,
                mode=safe_mode,
            )
            if heuristic:
                return heuristic
        if statement_type in _WRITE_STATEMENTS:
            requires_confirmation = True
        if safe_mode == "read_only" and statement_type in _WRITE_STATEMENTS:
            return {
                "ok": False,
                "error": "generated SQL is not read-only",
                "draft": data,
            }
        return {
            "ok": True,
            "request": question,
            "mode": safe_mode,
            "sql": sql_text,
            "statement_type": statement_type,
            "explanation": normalize_text(data.get("explanation")),
            "assumptions": data.get("assumptions") if isinstance(data.get("assumptions"), list) else [],
            "tables": data.get("tables") if isinstance(data.get("tables"), list) else [],
            "requires_confirmation": requires_confirmation,
            "schema_table_count": int(schema_snapshot.get("table_count") or 0),
        }

    def execute_sql_with_audit(
        self,
        *,
        sql: str,
        params: list[Any] | None = None,
        confirmed: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
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
        if not _is_single_statement(sql_text):
            return {"ok": False, "error": "only a single SQL statement is allowed"}
        statement_type = _detect_statement_type(sql_text)
        if not statement_type:
            return {"ok": False, "error": "unable to detect SQL statement type"}
        if statement_type in _WRITE_STATEMENTS and not confirmed:
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
                normalized_params = _normalize_params(params)
                if statement_type in _READ_STATEMENTS:
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
    def _render_schema_context(schema_snapshot: dict[str, Any]) -> str:
        lines: list[str] = []
        for table in schema_snapshot.get("tables", []) if isinstance(schema_snapshot.get("tables"), list) else []:
            if not isinstance(table, dict):
                continue
            schema_name = normalize_text(table.get("schema")) or "public"
            table_name = normalize_text(table.get("table_name"))
            if not table_name:
                continue
            lines.append(f"- {schema_name}.{table_name}")
            for column in table.get("columns", []) if isinstance(table.get("columns"), list) else []:
                if not isinstance(column, dict):
                    continue
                column_name = normalize_text(column.get("name"))
                data_type = normalize_text(column.get("data_type") or column.get("udt_name"))
                nullable = "NULL" if column.get("nullable") else "NOT NULL"
                lines.append(f"  - {column_name}: {data_type} {nullable}")
            primary_key = table.get("primary_key") if isinstance(table.get("primary_key"), list) else []
            if primary_key:
                lines.append(f"  - primary_key: {', '.join(str(value) for value in primary_key)}")
        return "\n".join(lines).strip()

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


class Assistant1SchemaTools:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        provider: Assistant1ResponsesProvider | None = None,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = provider or Assistant1ResponsesProvider(self.settings)

    def design_schema_draft(
        self,
        *,
        objective: str,
        table_name: str = "",
        fields: list[dict[str, Any]] | None = None,
        expected_queries: list[str] | None = None,
        file_context: str = "",
    ) -> dict[str, Any]:
        text = normalize_text(objective)
        if not text:
            return {"ok": False, "error": "objective is required"}
        if not self.provider.configured:
            return {"ok": False, "error": "chat provider is not configured for schema design"}

        prompt = (
            "请根据下面的需求设计 PostgreSQL 表结构草案。\n"
            "只输出 JSON 对象，不要输出 markdown。\n"
            "JSON 键固定为：design_summary, tables, assumptions。\n"
            "tables 中每个元素包含：name, purpose, columns, primary_key, unique_constraints, indexes。\n"
            "columns 中每个元素包含：name, type, nullable, description。\n"
            "默认优先设计 1 到 2 张表，只有确实必要时才增加更多表。\n"
            "字段说明保持简洁，避免大段解释。\n"
        )
        if table_name:
            prompt += f"优先考虑表名：{normalize_text(table_name)}。\n"
        if fields:
            prompt += "候选字段：\n" + json.dumps(fields, ensure_ascii=False, indent=2) + "\n"
        if expected_queries:
            prompt += "预期查询：\n" + json.dumps(expected_queries, ensure_ascii=False, indent=2) + "\n"
        if file_context:
            prompt += f"文档上下文摘要：\n{file_context}\n"
        prompt += f"\n设计目标：{text}"

        result = self.provider.complete(
            messages=[{"role": "user", "content": prompt}],
            instructions=(
                "你是 PostgreSQL 表结构设计助手。"
                "输出 JSON 对象即可。"
                "设计结果要尽量规范、易查询、便于后续 NL2SQL 和审计。"
            ),
            max_output_tokens=min(1800, self.settings.chat_max_output_tokens),
            reasoning_effort="minimal",
            text_verbosity="medium",
            metadata={"assistant_runtime": "assistant_1", "phase": "design_schema_draft"},
        )
        try:
            data = _extract_json_object(result.output_text)
        except Exception as exc:
            return {
                "ok": True,
                "objective": text,
                **self._fallback_schema_design(
                    objective=text,
                    fallback_table_name=table_name,
                    fields=fields or [],
                    parse_error=f"{type(exc).__name__}: {exc}",
                ),
            }

        normalized = self._normalize_schema_design(
            data=data,
            objective=text,
            fallback_table_name=table_name,
        )
        return {
            "ok": True,
            "objective": text,
            **normalized,
        }

    def _normalize_schema_design(
        self,
        *,
        data: dict[str, Any],
        objective: str,
        fallback_table_name: str,
    ) -> dict[str, Any]:
        raw_tables = data.get("tables") if isinstance(data.get("tables"), list) else []
        tables: list[dict[str, Any]] = []
        for index, table in enumerate(raw_tables, start=1):
            if not isinstance(table, dict):
                continue
            table_name = self._safe_table_name(table.get("name") or fallback_table_name or f"assistant1_table_{index}")
            purpose = normalize_text(table.get("purpose")) or objective
            columns = self._normalize_columns(table.get("columns"))
            if not columns:
                columns = [
                    {"name": "id", "type": "uuid", "nullable": False, "description": "primary key"},
                    {"name": "created_at", "type": "timestamptz", "nullable": False, "description": "creation time"},
                ]
            primary_key = [self._safe_column_name(value) for value in table.get("primary_key", []) if self._safe_column_name(value)]
            if not primary_key and any(column["name"] == "id" for column in columns):
                primary_key = ["id"]
            unique_constraints = [
                [self._safe_column_name(name) for name in group if self._safe_column_name(name)]
                for group in table.get("unique_constraints", [])
                if isinstance(group, list)
            ]
            indexes = []
            for item in table.get("indexes", []) if isinstance(table.get("indexes"), list) else []:
                if not isinstance(item, dict):
                    continue
                columns_list = [self._safe_column_name(name) for name in item.get("columns", []) if self._safe_column_name(name)]
                if not columns_list:
                    continue
                indexes.append(
                    {
                        "name": self._safe_table_name(item.get("name") or f"idx_{table_name}_{'_'.join(columns_list)}"),
                        "columns": columns_list,
                        "unique": bool(item.get("unique")),
                    }
                )
            tables.append(
                {
                    "name": table_name,
                    "purpose": purpose,
                    "columns": columns,
                    "primary_key": primary_key,
                    "unique_constraints": [group for group in unique_constraints if group],
                    "indexes": indexes,
                }
            )

        if not tables:
            fallback_name = self._safe_table_name(fallback_table_name or "assistant1_records")
            tables = [
                {
                    "name": fallback_name,
                    "purpose": objective,
                    "columns": [
                        {"name": "id", "type": "uuid", "nullable": False, "description": "primary key"},
                        {"name": "source_text", "type": "text", "nullable": False, "description": "original content"},
                        {"name": "created_at", "type": "timestamptz", "nullable": False, "description": "creation time"},
                    ],
                    "primary_key": ["id"],
                    "unique_constraints": [],
                    "indexes": [],
                }
            ]

        ddl_statements: list[str] = []
        for table in tables:
            ddl_statements.extend(self._build_table_ddl(table))
        return {
            "design_summary": normalize_text(data.get("design_summary")) or objective,
            "tables": tables,
            "ddl_statements": ddl_statements,
            "assumptions": data.get("assumptions") if isinstance(data.get("assumptions"), list) else [],
        }

    def _fallback_schema_design(
        self,
        *,
        objective: str,
        fallback_table_name: str,
        fields: list[dict[str, Any]],
        parse_error: str,
    ) -> dict[str, Any]:
        table_name = self._safe_table_name(fallback_table_name or "assistant1_records")
        if fields:
            columns = self._normalize_columns(fields)
        else:
            columns = [
                {"name": "id", "type": "uuid", "nullable": False, "description": "primary key"},
            ]
            lower_objective = objective.lower()
            if any(marker in objective for marker in ("年", "年度", "year")):
                columns.append({"name": "stat_year", "type": "integer", "nullable": False, "description": "stat year"})
            if any(marker in objective for marker in ("指标", "metric", "名称")):
                columns.append({"name": "indicator_name", "type": "text", "nullable": False, "description": "indicator name"})
            if any(marker in objective for marker in ("值", "value", "数值")):
                columns.append({"name": "indicator_value", "type": "numeric(18,4)", "nullable": True, "description": "indicator value"})
            if any(marker in objective for marker in ("单位", "unit")):
                columns.append({"name": "unit", "type": "text", "nullable": True, "description": "value unit"})
            if any(marker in objective for marker in ("页面", "page", "页码")):
                columns.append({"name": "source_page", "type": "integer", "nullable": True, "description": "source page"})
            columns.extend(
                [
                    {"name": "source_file_hash", "type": "text", "nullable": True, "description": "source document hash"},
                    {"name": "created_at", "type": "timestamptz", "nullable": False, "description": "creation time"},
                ]
            )
        unique_columns = []
        seen: set[str] = set()
        for column in columns:
            if column["name"] in seen:
                continue
            seen.add(column["name"])
            unique_columns.append(column)
        table = {
            "name": table_name,
            "purpose": objective,
            "columns": unique_columns,
            "primary_key": ["id"] if any(column["name"] == "id" for column in unique_columns) else [],
            "unique_constraints": [],
            "indexes": [],
        }
        return {
            "design_summary": objective,
            "tables": [table],
            "ddl_statements": self._build_table_ddl(table),
            "assumptions": [
                "Returned a deterministic fallback design because the model output was not valid JSON.",
                f"parse_error={parse_error}",
            ],
        }

    @staticmethod
    def _normalize_columns(raw_columns: Any) -> list[dict[str, Any]]:
        columns: list[dict[str, Any]] = []
        for item in raw_columns if isinstance(raw_columns, list) else []:
            if not isinstance(item, dict):
                continue
            name = Assistant1SchemaTools._safe_column_name(item.get("name"))
            column_type = normalize_text(item.get("type")) or "text"
            if not name:
                continue
            columns.append(
                {
                    "name": name,
                    "type": column_type,
                    "nullable": bool(item.get("nullable", True)),
                    "description": normalize_text(item.get("description")),
                }
            )
        return columns

    @staticmethod
    def _safe_table_name(value: Any) -> str:
        text = normalize_text(value).lower().replace("-", "_")
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        return text[:63] or "assistant1_table"

    @staticmethod
    def _safe_column_name(value: Any) -> str:
        text = normalize_text(value).lower().replace("-", "_")
        text = re.sub(r"[^a-z0-9_]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        if text and text[0].isdigit():
            text = f"col_{text}"
        return text[:63]

    @staticmethod
    def _build_table_ddl(table: dict[str, Any]) -> list[str]:
        table_name = _quote_ident(table["name"])
        column_defs: list[str] = []
        for column in table.get("columns", []):
            name = _quote_ident(column["name"])
            nullable = "" if column.get("nullable", True) else " NOT NULL"
            column_defs.append(f"    {name} {column['type']}{nullable}")
        if table.get("primary_key"):
            pk = ", ".join(_quote_ident(name) for name in table["primary_key"])
            column_defs.append(f"    PRIMARY KEY ({pk})")
        for unique_group in table.get("unique_constraints", []):
            if unique_group:
                unique_sql = ", ".join(_quote_ident(name) for name in unique_group)
                column_defs.append(f"    UNIQUE ({unique_sql})")
        statements = [f"CREATE TABLE IF NOT EXISTS {table_name} (\n" + ",\n".join(column_defs) + "\n);"]
        for index in table.get("indexes", []):
            unique = "UNIQUE " if index.get("unique") else ""
            index_name = _quote_ident(index["name"])
            index_cols = ", ".join(_quote_ident(name) for name in index["columns"])
            statements.append(f"CREATE {unique}INDEX IF NOT EXISTS {index_name} ON {table_name} ({index_cols});")
        return statements

    @staticmethod
    def _heuristic_sql_draft(
        *,
        request: str,
        allowed_tables: list[str],
        schema_snapshot: dict[str, Any],
        mode: str,
    ) -> dict[str, Any] | None:
        if mode != "read_only":
            return None
        question = normalize_text(request).lower()
        available_tables = [
            normalize_text(item.get("table_name"))
            for item in schema_snapshot.get("tables", [])
            if isinstance(item, dict) and normalize_text(item.get("table_name"))
        ]
        preferred_tables = [normalize_text(name) for name in allowed_tables if normalize_text(name)] or available_tables
        if not preferred_tables:
            return None
        target_table = ""
        for table_name in preferred_tables:
            if table_name.lower() in question:
                target_table = table_name
                break
        if not target_table:
            target_table = preferred_tables[0]
        if any(marker in question for marker in ("多少", "总数", "count", "几条", "共有")):
            sql = f'SELECT COUNT(*) AS row_count FROM {_quote_ident(target_table)};'
            return {
                "ok": True,
                "request": request,
                "mode": mode,
                "sql": sql,
                "statement_type": "select",
                "explanation": "Heuristic COUNT(*) fallback based on a single-table count request.",
                "assumptions": [f"Assumed target table is {target_table}."],
                "tables": [target_table],
                "requires_confirmation": False,
                "schema_table_count": int(schema_snapshot.get("table_count") or 0),
            }
        if any(marker in question for marker in ("列出", "查看", "展示", "返回")):
            sql = f'SELECT * FROM {_quote_ident(target_table)} LIMIT 50;'
            return {
                "ok": True,
                "request": request,
                "mode": mode,
                "sql": sql,
                "statement_type": "select",
                "explanation": "Heuristic preview query fallback.",
                "assumptions": [f"Assumed target table is {target_table}."],
                "tables": [target_table],
                "requires_confirmation": False,
                "schema_table_count": int(schema_snapshot.get("table_count") or 0),
            }
        return None
