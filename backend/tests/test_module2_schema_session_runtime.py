from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


schema_session_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "schema", "schema_session_runtime.py"],
    "_smart_doc_flow_module2_schema_session_runtime",
)

SchemaSessionRuntime = schema_session_runtime_module.SchemaSessionRuntime


def test_schema_session_runtime_builds_schema_context_and_allows_llm_when_eligible() -> None:
    runtime = SchemaSessionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_AUTO_SCHEMA_LLM_MAX_FILE_MB": "1.5",
            "MODULE2_AUTO_SCHEMA_LLM_MAX_CONTEXT_CHARS": "6400",
        }.get(key, default)
    )
    resolve_calls: list[dict[str, object]] = []
    context_calls: list[dict[str, object]] = []

    async def _resolve_effective_schema(**kwargs):
        resolve_calls.append(dict(kwargs))
        return (
            {"fields": {"project_name": {"type": "string"}}},
            {"source": "request", "field_count": 1},
        )

    def _detect_domain_template(**kwargs):
        assert kwargs["file_name"] == "demo.pdf"
        return "common_document"

    def _extract_text_for_schema(markdown, table_blocks, figure_blocks, *, max_chars):
        context_calls.append(
            {
                "markdown": markdown,
                "table_count": len(table_blocks),
                "figure_count": len(figure_blocks),
                "max_chars": max_chars,
            }
        )
        return "schema preview"

    def _resolve_dynamic_extract_timeout_sec(**kwargs):
        raise AssertionError("dynamic timeout should not run for pdf files")

    async def _run():
        return await runtime.resolve_session(
            file_name="demo.pdf",
            file_bytes=b"x" * (1024 * 1024),
            markdown="demo markdown",
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[],
            requested_schema={"fields": {"project_name": "string"}},
            profile_hint="mixed",
            extract_timeout_sec=120.0,
            detect_domain_template=_detect_domain_template,
            extract_text_for_schema=_extract_text_for_schema,
            resolve_effective_schema=_resolve_effective_schema,
            resolve_dynamic_extract_timeout_sec=_resolve_dynamic_extract_timeout_sec,
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
        )

    outcome = asyncio.run(_run())
    assert outcome.naming_template == "common_document"
    assert outcome.schema_context_preview == "schema preview"
    assert outcome.allow_schema_llm is True
    assert outcome.effective_schema_fields == {"project_name": {"type": "string"}}
    assert outcome.extract_timeout_sec == 120.0
    assert outcome.dynamic_extract_timeout_meta == {}
    assert round(outcome.file_size_mb, 2) == 1.0
    assert context_calls == [
        {
            "markdown": "demo markdown",
            "table_count": 1,
            "figure_count": 0,
            "max_chars": 6400,
        }
    ]
    assert resolve_calls[0]["naming_template"] == "common_document"
    assert resolve_calls[0]["allow_llm"] is True
    assert resolve_calls[0]["profile_hint"] == "mixed"


def test_schema_session_runtime_disables_llm_for_large_word_file_and_applies_dynamic_timeout() -> None:
    runtime = SchemaSessionRuntime(
        getenv=lambda key, default=None: {
            "MODULE2_AUTO_SCHEMA_LLM_MAX_FILE_MB": "1.0",
            "MODULE2_AUTO_SCHEMA_LLM_MAX_CONTEXT_CHARS": "4096",
        }.get(key, default)
    )
    resolve_calls: list[dict[str, object]] = []
    timeout_calls: list[dict[str, object]] = []

    async def _resolve_effective_schema(**kwargs):
        resolve_calls.append(dict(kwargs))
        return (
            {"fields": {"invoice_total": {"type": "number"}}},
            {"source": "auto", "field_count": 1},
        )

    def _resolve_dynamic_extract_timeout_sec(**kwargs):
        timeout_calls.append(dict(kwargs))
        return 240.0, {"applied": True, "resolved_timeout_sec": 240.0}

    async def _run():
        return await runtime.resolve_session(
            file_name="invoice.docx",
            file_bytes=b"x" * (2 * 1024 * 1024),
            markdown="invoice markdown",
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[],
            requested_schema={"mode": "auto"},
            profile_hint="table_heavy",
            extract_timeout_sec=90.0,
            detect_domain_template=lambda **kwargs: "finance_document",
            extract_text_for_schema=lambda *args, **kwargs: "schema preview",
            resolve_effective_schema=_resolve_effective_schema,
            resolve_dynamic_extract_timeout_sec=_resolve_dynamic_extract_timeout_sec,
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
        )

    outcome = asyncio.run(_run())
    assert outcome.allow_schema_llm is False
    assert outcome.extract_timeout_sec == 240.0
    assert outcome.dynamic_extract_timeout_meta == {"applied": True, "resolved_timeout_sec": 240.0}
    assert resolve_calls[0]["allow_llm"] is False
    assert timeout_calls[0]["file_name"] == "invoice.docx"
    assert timeout_calls[0]["schema_fields"] == {"invoice_total": {"type": "number"}}
