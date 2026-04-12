from __future__ import annotations

from typing import Any

from ..config import Assistant1Settings
from ..responses_provider import Assistant1ResponsesProvider
from ..text_utils import normalize_text
from .common import WRITE_STATEMENTS, detect_statement_type, extract_json_object, quote_ident
from .introspection import Assistant1DatabaseIntrospector


class Assistant1SqlDraftingService:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        provider: Assistant1ResponsesProvider | None = None,
        introspector: Assistant1DatabaseIntrospector | None = None,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = provider or Assistant1ResponsesProvider(self.settings)
        self.introspector = introspector or Assistant1DatabaseIntrospector(self.settings)

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
        try:
            schema_snapshot = self.introspector.inspect_database_schema(table_names=allowed_tables or [], include_columns=True)
        except Exception:
            schema_snapshot = {"ok": False, "table_count": 0, "tables": []}
        introspection_ok = bool(schema_snapshot.get("ok"))
        schema_offline = not introspection_ok
        if not self.provider.configured:
            return {"ok": False, "error": "chat provider is not configured for SQL drafting"}

        safe_mode = str(mode or "read_only").strip().lower()
        if safe_mode not in {"read_only", "read_write_draft"}:
            safe_mode = "read_only"

        schema_context = self._render_schema_context(schema_snapshot) if introspection_ok else ""
        prompt = (
            "根据下面的 PostgreSQL 数据库结构，把用户请求转换成 SQL 草案。\n"
            "只输出 JSON 对象，不要输出 markdown，也不要输出解释性的前后缀。\n"
            "JSON 键固定为：sql, statement_type, explanation, assumptions, tables, requires_confirmation。\n"
            "如果信息不足或请求和现有表结构不匹配，可以把 sql 设为空字符串，并在 explanation 里说明缺什么。\n"
            "如果用户在问数量、总数、多少条记录，优先使用 COUNT(*) 这类聚合 SQL。\n"
        )
        if safe_mode == "read_only":
            prompt += "本轮只允许生成只读 SQL（SELECT / WITH / EXPLAIN / SHOW），不要生成写操作。\n"
        else:
            prompt += "本轮可以生成写操作草案，但要明确是否需要确认。\n"
        if schema_context:
            prompt += f"\n数据库结构：\n{schema_context}\n\n用户请求：{question}"
        else:
            prompt += (
                "\n注意：当前数据库结构暂时不可用（空库或连接未就绪）。"
                "请仅基于用户请求推测合理的表名和字段，并在草案的 assumptions 字段里注明这些是推断，实际执行前需核对。\n"
                f"\n用户请求：{question}"
            )

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
            data = extract_json_object(result.output_text)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"failed to parse SQL draft JSON: {type(exc).__name__}: {exc}",
                "raw_text": result.output_text,
            }

        sql_text = str(data.get("sql") or "").strip()
        statement_type = detect_statement_type(sql_text) or str(data.get("statement_type") or "").strip().lower()
        requires_confirmation = bool(data.get("requires_confirmation"))
        if not sql_text:
            heuristic = self._heuristic_sql_draft(
                request=question,
                allowed_tables=allowed_tables or [],
                schema_snapshot=schema_snapshot,
                mode=safe_mode,
            )
            if heuristic:
                heuristic["schema_offline"] = schema_offline
                return heuristic
        if statement_type in WRITE_STATEMENTS:
            requires_confirmation = True
        if safe_mode == "read_only" and statement_type in WRITE_STATEMENTS:
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
            "schema_offline": schema_offline,
        }

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
            sql = f"SELECT COUNT(*) AS row_count FROM {quote_ident(target_table)};"
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
            sql = f"SELECT * FROM {quote_ident(target_table)} LIMIT 50;"
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
