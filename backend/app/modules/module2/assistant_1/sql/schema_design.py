from __future__ import annotations

import re
from typing import Any

from ..config import Assistant1Settings
from ..responses_provider import Assistant1ResponsesProvider
from ..text_utils import normalize_text
from .common import extract_json_object, quote_ident


class Assistant1SchemaDesignService:
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
            "优先给出最小但合理的表组，不要为了压缩表数量而牺牲规范化、审计和后续扩展性；通常 1 到 3 张表都可以。\n"
            "字段说明保持简洁，避免大段解释。\n"
        )
        if table_name:
            prompt += f"优先考虑表名：{normalize_text(table_name)}。\n"
        if fields:
            import json

            prompt += "候选字段：\n" + json.dumps(fields, ensure_ascii=False, indent=2) + "\n"
        if expected_queries:
            import json

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
            data = extract_json_object(result.output_text)
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
            columns = [{"name": "id", "type": "uuid", "nullable": False, "description": "primary key"}]
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
            name = Assistant1SchemaDesignService._safe_column_name(item.get("name"))
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
        table_name = quote_ident(table["name"])
        column_defs: list[str] = []
        for column in table.get("columns", []):
            name = quote_ident(column["name"])
            nullable = "" if column.get("nullable", True) else " NOT NULL"
            column_defs.append(f"    {name} {column['type']}{nullable}")
        if table.get("primary_key"):
            pk = ", ".join(quote_ident(name) for name in table["primary_key"])
            column_defs.append(f"    PRIMARY KEY ({pk})")
        for unique_group in table.get("unique_constraints", []):
            if unique_group:
                unique_sql = ", ".join(quote_ident(name) for name in unique_group)
                column_defs.append(f"    UNIQUE ({unique_sql})")
        statements = [f"CREATE TABLE IF NOT EXISTS {table_name} (\n" + ",\n".join(column_defs) + "\n);"]
        for index in table.get("indexes", []):
            unique = "UNIQUE " if index.get("unique") else ""
            index_name = quote_ident(index["name"])
            index_cols = ", ".join(quote_ident(name) for name in index["columns"])
            statements.append(f"CREATE {unique}INDEX IF NOT EXISTS {index_name} ON {table_name} ({index_cols});")
        return statements
