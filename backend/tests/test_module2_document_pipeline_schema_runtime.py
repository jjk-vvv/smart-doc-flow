from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace


document_pipeline_schema_runtime_module = importlib.import_module("app.modules.module2.core.pipeline.document_pipeline_stages_runtime")
DocumentPipelineSchemaRuntime = document_pipeline_schema_runtime_module.DocumentPipelineSchemaRuntime


class _AsyncNoopSemaphore:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Logger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def info(self, message: str, *args) -> None:
        self.calls.append((message, args))


class _SchemaSessionRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def resolve_session(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            naming_template="finance_document",
            schema_context_preview="schema preview",
            allow_schema_llm=True,
            effective_schema={"fields": {"amount": {"type": "number"}}},
            schema_meta={"source": "auto", "naming_template": "finance_document"},
            effective_schema_fields={"amount": {"type": "number"}},
            extract_timeout_sec=210.0,
            dynamic_extract_timeout_meta={"boost": True},
            file_size_mb=0.42,
        )


def test_document_pipeline_schema_runtime_resolves_schema_session_handoff() -> None:
    runtime = DocumentPipelineSchemaRuntime()
    schema_session_runtime = _SchemaSessionRuntime()
    logger = _Logger()

    outcome = asyncio.run(
        runtime.resolve(
            file_name="demo.docx",
            file_bytes=b"docx",
            marked_markdown="markdown",
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            requested_schema={"fields": {"amount": {"type": "number"}}},
            nonpdf_preflight={"profile": "mixed"},
            extract_timeout_sec=160.0,
            schema_session_runtime=schema_session_runtime,
            extraction_llm_semaphore=_AsyncNoopSemaphore(),
            detect_domain_template=lambda **kwargs: "finance_document",
            extract_text_for_schema=lambda *args, **kwargs: "schema preview",
            resolve_effective_schema=lambda **kwargs: ({"fields": {}}, {"source": "auto"}),
            resolve_dynamic_extract_timeout_sec=lambda **kwargs: (210.0, {"boost": True}),
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
            logger=logger,
        )
    )

    assert schema_session_runtime.calls[0]["profile_hint"] == "mixed"
    assert outcome.naming_template == "finance_document"
    assert outcome.schema_meta == {"source": "auto", "naming_template": "finance_document"}
    assert outcome.effective_schema_fields == {"amount": {"type": "number"}}
    assert outcome.extract_timeout_sec == 210.0
    assert outcome.dynamic_extract_timeout_meta == {"boost": True}
    assert outcome.file_size_mb == 0.42
    assert len(logger.calls) == 1
