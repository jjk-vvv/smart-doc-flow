from __future__ import annotations

from typing import Any

import asyncpg

from ..config import Assistant1Settings
from ..text_utils import normalize_text


class Assistant1DatabaseIntrospector:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()

    def inspect_database_schema(
        self,
        *,
        schemas: list[str] | None = None,
        table_names: list[str] | None = None,
        include_columns: bool = True,
    ) -> dict[str, Any]:
        import asyncio

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
                    """
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
