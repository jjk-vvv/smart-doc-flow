from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Tuple


@dataclass(frozen=True)
class SchemaSessionOutcome:
    naming_template: str
    schema_context_preview: str
    allow_schema_llm: bool
    effective_schema: Dict[str, Any]
    schema_meta: Dict[str, Any]
    effective_schema_fields: Dict[str, Any]
    extract_timeout_sec: float
    dynamic_extract_timeout_meta: Dict[str, Any]
    file_size_mb: float


class SchemaSessionRuntime:
    """Prepare schema-resolution session state without changing extraction semantics."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    async def resolve_session(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        markdown: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        requested_schema: Dict[str, Any],
        profile_hint: str,
        extract_timeout_sec: float,
        detect_domain_template: Callable[..., str],
        extract_text_for_schema: Callable[..., str],
        resolve_effective_schema: Callable[..., Awaitable[Tuple[Dict[str, Any], Dict[str, Any]]]],
        resolve_dynamic_extract_timeout_sec: Callable[..., Tuple[float, Dict[str, Any]]],
        is_word_file: Callable[[str], bool],
    ) -> SchemaSessionOutcome:
        naming_template = detect_domain_template(
            file_name=file_name,
            markdown=markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
        )
        auto_schema_llm_max_mb = max(
            0.2,
            float(self._getenv("MODULE2_AUTO_SCHEMA_LLM_MAX_FILE_MB", "1.2")),
        )
        auto_schema_llm_max_context_chars = max(
            2400,
            int(self._getenv("MODULE2_AUTO_SCHEMA_LLM_MAX_CONTEXT_CHARS", "10000")),
        )
        schema_context_preview = extract_text_for_schema(
            markdown,
            table_blocks,
            figure_blocks,
            max_chars=auto_schema_llm_max_context_chars,
        )
        file_size_mb = len(file_bytes) / (1024.0 * 1024.0)
        allow_schema_llm = bool(schema_context_preview) and len(table_blocks) <= 14 and len(figure_blocks) <= 16 and (
            file_size_mb <= auto_schema_llm_max_mb or bool(figure_blocks)
        )
        effective_schema, schema_meta = await resolve_effective_schema(
            requested_schema=requested_schema,
            file_name=file_name,
            markdown=markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            profile_hint=profile_hint,
            naming_template=naming_template,
            allow_llm=allow_schema_llm,
        )
        effective_schema_fields = (
            effective_schema.get("fields")
            if isinstance(effective_schema.get("fields"), dict)
            else {}
        )
        dynamic_extract_timeout_meta: Dict[str, Any] = {}
        resolved_extract_timeout_sec = float(extract_timeout_sec)
        if is_word_file(file_name):
            resolved_extract_timeout_sec, dynamic_extract_timeout_meta = resolve_dynamic_extract_timeout_sec(
                file_name=file_name,
                extract_timeout_sec=extract_timeout_sec,
                markdown=markdown,
                schema_fields=effective_schema_fields,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
            )
        return SchemaSessionOutcome(
            naming_template=naming_template,
            schema_context_preview=schema_context_preview,
            allow_schema_llm=allow_schema_llm,
            effective_schema=effective_schema,
            schema_meta=schema_meta,
            effective_schema_fields=effective_schema_fields,
            extract_timeout_sec=resolved_extract_timeout_sec,
            dynamic_extract_timeout_meta=dynamic_extract_timeout_meta,
            file_size_mb=file_size_mb,
        )
