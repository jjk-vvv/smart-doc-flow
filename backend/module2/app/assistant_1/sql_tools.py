from __future__ import annotations

from typing import Any

from .config import Assistant1Settings
from .responses_provider import Assistant1ResponsesProvider
from .sql import (
    Assistant1DatabaseIntrospector,
    Assistant1SchemaDesignService,
    Assistant1SqlDraftingService,
    Assistant1SqlExecutionService,
)


class Assistant1SqlTools:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        provider: Assistant1ResponsesProvider | None = None,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = provider or Assistant1ResponsesProvider(self.settings)
        self.introspector = Assistant1DatabaseIntrospector(self.settings)
        self.drafting_service = Assistant1SqlDraftingService(
            self.settings,
            self.provider,
            self.introspector,
        )
        self.execution_service = Assistant1SqlExecutionService(self.settings)

    def inspect_database_schema(
        self,
        *,
        schemas: list[str] | None = None,
        table_names: list[str] | None = None,
        include_columns: bool = True,
    ) -> dict[str, Any]:
        return self.introspector.inspect_database_schema(
            schemas=schemas,
            table_names=table_names,
            include_columns=include_columns,
        )

    def draft_sql_from_nl(
        self,
        *,
        request: str,
        allowed_tables: list[str] | None = None,
        mode: str = "read_only",
    ) -> dict[str, Any]:
        return self.drafting_service.draft_sql_from_nl(
            request=request,
            allowed_tables=allowed_tables,
            mode=mode,
        )

    def execute_sql_with_audit(
        self,
        *,
        sql: str,
        params: list[Any] | None = None,
        confirmed: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        return self.execution_service.execute_sql_with_audit(
            sql=sql,
            params=params,
            confirmed=confirmed,
            reason=reason,
        )


class Assistant1SchemaTools:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        provider: Assistant1ResponsesProvider | None = None,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = provider or Assistant1ResponsesProvider(self.settings)
        self.design_service = Assistant1SchemaDesignService(self.settings, self.provider)

    def design_schema_draft(
        self,
        *,
        objective: str,
        table_name: str = "",
        fields: list[dict[str, Any]] | None = None,
        expected_queries: list[str] | None = None,
        file_context: str = "",
    ) -> dict[str, Any]:
        return self.design_service.design_schema_draft(
            objective=objective,
            table_name=table_name,
            fields=fields,
            expected_queries=expected_queries,
            file_context=file_context,
        )
