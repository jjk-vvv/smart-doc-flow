from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


document_pipeline_runtime_module = importlib.import_module("app.modules.module2.core.pipeline.document_pipeline_runtime")

DocumentPipelineRuntime = document_pipeline_runtime_module.DocumentPipelineRuntime
DocumentPipelineInputBundle = document_pipeline_runtime_module.DocumentPipelineInputBundle
DocumentPipelineParseBundle = document_pipeline_runtime_module.DocumentPipelineParseBundle
DocumentPipelineSchemaBundle = document_pipeline_runtime_module.DocumentPipelineSchemaBundle
DocumentPipelineGraphBundle = document_pipeline_runtime_module.DocumentPipelineGraphBundle


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


class _DocumentInputPlanRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_plan(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_timeout_sec=120.0,
            extract_timeout_sec=180.0,
            nonpdf_preflight={"profile": "mixed"},
            nonpdf_budget={"parse_timeout_sec": 60.0},
            nonpdf_total_budget_sec=240.0,
            nonpdf_guard_sec=2.0,
            word_parse_extract_budget_sec=70.0,
            word_convert_budget_sec=35.0,
            word_parse_via_pdf=True,
            input_is_word=True,
        )


class _WordInputPreparationRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def prepare(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            parse_track="VisualTrack",
            parse_warning="word-warning",
            conversion_diag={"office_pdf_converted": True},
            word_suffix=".docx",
        )


class _ParsePreparationRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def prepare(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_timeout_sec=100.0,
            extract_timeout_sec=160.0,
            parse_warning="parse-warning",
            parse_source_file_name="source.docx",
            parse_source_file_bytes=b"docx",
            progress_message="parsing",
            progress_extra={"stage": "parsing"},
            parse_attempt_runner="runner",
        )


class _DocumentParseRecoveryRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            marked_markdown="markdown",
            bbox_map={"r1": [1.0]},
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            parse_stats={"pipeline": "visual_first", "chain_status": "success"},
            parse_track="VisualTrack",
            parse_warning="recovery-warning",
        )


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


class _ExtractionGraphRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            final_state={"results": {"amount": {"value": 100}}, "errors": [], "soft_warnings": []},
            extract_ms=234,
            used_quick_fallback=False,
        )


class _PerfCounter:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        if len(self._values) == 1:
            return self._values[0]
        return self._values.pop(0)


async def _resolve_effective_schema():
    return {"fields": {"amount": {"type": "number"}}}, {"source": "auto", "naming_template": "finance_document"}


async def _record_progress(events, stage, ratio, message, extra=None):
    events.append((stage, ratio, message, dict(extra or {})))


def _build_runtime(
    *,
    build_visual_chain_contract=None,
    document_pipeline_input_runtime=None,
    document_pipeline_parse_runtime=None,
    document_pipeline_schema_runtime=None,
    document_pipeline_graph_runtime=None,
    direct_semantic_extract_runtime=None,
    use_dependency_bundles: bool = False,
):
    logger = _Logger()
    input_plan_runtime = _DocumentInputPlanRuntime()
    word_input_runtime = _WordInputPreparationRuntime()
    parse_preparation_runtime = _ParsePreparationRuntime()
    parse_recovery_runtime = _DocumentParseRecoveryRuntime()
    schema_session_runtime = _SchemaSessionRuntime()
    extraction_graph_runtime = _ExtractionGraphRuntime()
    preflight_nonpdf_profile = lambda **kwargs: {"profile": "mixed"}
    resolve_nonpdf_budgets = lambda profile: {"parse_timeout_sec": 60.0, "extract_timeout_sec": 90.0}
    resolve_nonpdf_plan = lambda **kwargs: SimpleNamespace(
        parse_timeout_sec=60.0,
        extract_timeout_sec=90.0,
        nonpdf_total_budget_sec=180.0,
        word_parse_extract_budget_sec=70.0,
        word_convert_budget_sec=35.0,
    )
    apply_field_extract_timeout_floor = lambda extract_timeout_sec: extract_timeout_sec
    is_word_file = lambda file_name: file_name.lower().endswith(".docx")
    office_convert_enabled = lambda: True
    docx_native_recovery_enabled = lambda: True
    validate_word_preconditions = lambda **kwargs: SimpleNamespace(
        should_raise=False,
        terminal_status_code=None,
        terminal_detail="",
    )
    resolve_conversion_timeout = lambda **kwargs: SimpleNamespace(timeout_sec=30.0, exhausted_detail="")
    build_word_pdf_success = lambda **kwargs: {}
    resolve_word_pdf_failure = lambda **kwargs: SimpleNamespace(
        conversion_diag={},
        emit_progress_message="",
        should_raise=False,
        terminal_status_code=None,
        terminal_detail="",
        parse_track="FastTrack",
        use_original_input=True,
        parse_warning="",
    )
    build_doc_to_docx_success = lambda **kwargs: {}
    build_doc_to_docx_failure = lambda **kwargs: {}
    word_pdf_semaphore = _AsyncNoopSemaphore()
    ensure_preview_job_started = lambda **kwargs: None
    await_or_reuse_pdf = lambda **kwargs: None
    run_with_progress_heartbeat = lambda coro, **kwargs: coro
    convert_doc_to_docx_with_timeout = lambda **kwargs: (b"", {})
    tighten_parse_budgets_before_parse = lambda **kwargs: SimpleNamespace(
        parse_timeout_sec=kwargs["parse_timeout_sec"],
        extract_timeout_sec=kwargs["extract_timeout_sec"],
        tightened=False,
        warning="",
    )
    build_parse_session = lambda **kwargs: {
        "parse_timeout_sec": kwargs["parse_timeout_sec"],
        "progress_message": "parsing",
        "progress_extra": {"track": kwargs["parse_track"]},
        "parse_source_file_name": kwargs["file_name"],
        "parse_source_file_bytes": kwargs["file_bytes"],
    }
    build_parse_attempt_runner = lambda **kwargs: "runner"
    acquire_parse_execution_slots = lambda track: _AsyncNoopSemaphore()
    run_parse_in_process_pool = lambda **kwargs: None
    resolve_parse_progress_ramp_sec = lambda **kwargs: 1.0
    unpack_parse_output = lambda payload: payload
    visual_parse_policy_runtime = SimpleNamespace()
    parse_fallback_coordinator_runtime = SimpleNamespace()
    docx_native_recovery_runtime = SimpleNamespace()
    fasttrack_fallback_runtime = SimpleNamespace()
    visual_chain_required = lambda: True
    visual_strict_mode = lambda: True
    disable_fasttrack_fallback = lambda: False
    build_visual_chain_contract = build_visual_chain_contract or (
        lambda **kwargs: {"required": True, "satisfied": True, "reasons": []}
    )
    extraction_llm_semaphore = _AsyncNoopSemaphore()
    detect_domain_template = lambda **kwargs: "finance_document"
    extract_text_for_schema = lambda *args, **kwargs: "schema preview"
    resolve_effective_schema = lambda **kwargs: _resolve_effective_schema()
    resolve_dynamic_extract_timeout_sec = lambda **kwargs: (210.0, {"boost": True})
    run_graph = lambda state: state
    resolve_extract_progress_ramp_sec = lambda **kwargs: 1.0
    quick_extract_from_tables = lambda **kwargs: {}
    disable_quick_table_fallback = lambda: False

    runtime_kwargs = {
        "build_visual_chain_contract": build_visual_chain_contract,
        "logger": logger,
        "document_pipeline_input_runtime": document_pipeline_input_runtime,
        "document_pipeline_parse_runtime": document_pipeline_parse_runtime,
        "document_pipeline_schema_runtime": document_pipeline_schema_runtime,
        "document_pipeline_graph_runtime": document_pipeline_graph_runtime,
        "direct_semantic_extract_runtime": direct_semantic_extract_runtime,
        "perf_counter": _PerfCounter([100.0, 101.25]),
    }
    if use_dependency_bundles:
        runtime_kwargs.update(
            {
                "input_bundle": DocumentPipelineInputBundle(
                    document_input_plan_runtime=input_plan_runtime,
                    word_input_preparation_runtime=word_input_runtime,
                    preflight_nonpdf_profile=preflight_nonpdf_profile,
                    resolve_nonpdf_budgets=resolve_nonpdf_budgets,
                    resolve_nonpdf_plan=resolve_nonpdf_plan,
                    apply_field_extract_timeout_floor=apply_field_extract_timeout_floor,
                    word_pdf_required=lambda: True,
                    is_word_file=is_word_file,
                    office_convert_enabled=office_convert_enabled,
                    docx_native_recovery_enabled=docx_native_recovery_enabled,
                    validate_word_preconditions=validate_word_preconditions,
                    resolve_conversion_timeout=resolve_conversion_timeout,
                    build_word_pdf_success=build_word_pdf_success,
                    resolve_word_pdf_failure=resolve_word_pdf_failure,
                    build_doc_to_docx_success=build_doc_to_docx_success,
                    build_doc_to_docx_failure=build_doc_to_docx_failure,
                    word_pdf_semaphore=word_pdf_semaphore,
                    ensure_preview_job_started=ensure_preview_job_started,
                    await_or_reuse_pdf=await_or_reuse_pdf,
                    run_with_progress_heartbeat=run_with_progress_heartbeat,
                    convert_doc_to_docx_with_timeout=convert_doc_to_docx_with_timeout,
                ),
                "parse_bundle": DocumentPipelineParseBundle(
                    parse_preparation_runtime=parse_preparation_runtime,
                    document_parse_recovery_runtime=parse_recovery_runtime,
                    tighten_parse_budgets_before_parse=tighten_parse_budgets_before_parse,
                    build_parse_session=build_parse_session,
                    build_parse_attempt_runner=build_parse_attempt_runner,
                    acquire_parse_execution_slots=acquire_parse_execution_slots,
                    run_parse_in_process_pool=run_parse_in_process_pool,
                    run_with_progress_heartbeat=run_with_progress_heartbeat,
                    resolve_parse_progress_ramp_sec=resolve_parse_progress_ramp_sec,
                    unpack_parse_output=unpack_parse_output,
                    visual_parse_policy_runtime=visual_parse_policy_runtime,
                    parse_fallback_coordinator_runtime=parse_fallback_coordinator_runtime,
                    docx_native_recovery_runtime=docx_native_recovery_runtime,
                    fasttrack_fallback_runtime=fasttrack_fallback_runtime,
                    is_word_file=is_word_file,
                    visual_chain_required=visual_chain_required,
                    docx_native_recovery_enabled=docx_native_recovery_enabled,
                    visual_strict_mode=visual_strict_mode,
                    disable_fasttrack_fallback=disable_fasttrack_fallback,
                ),
                "schema_bundle": DocumentPipelineSchemaBundle(
                    schema_session_runtime=schema_session_runtime,
                    extraction_llm_semaphore=extraction_llm_semaphore,
                    detect_domain_template=detect_domain_template,
                    extract_text_for_schema=extract_text_for_schema,
                    resolve_effective_schema=resolve_effective_schema,
                    resolve_dynamic_extract_timeout_sec=resolve_dynamic_extract_timeout_sec,
                    is_word_file=is_word_file,
                ),
                "graph_bundle": DocumentPipelineGraphBundle(
                    extraction_graph_runtime=extraction_graph_runtime,
                    run_graph=run_graph,
                    extraction_llm_semaphore=extraction_llm_semaphore,
                    run_with_progress_heartbeat=run_with_progress_heartbeat,
                    resolve_extract_progress_ramp_sec=resolve_extract_progress_ramp_sec,
                    quick_extract_from_tables=quick_extract_from_tables,
                    disable_quick_table_fallback=disable_quick_table_fallback,
                ),
            }
        )
    else:
        runtime_kwargs.update(
            {
                "document_input_plan_runtime": input_plan_runtime,
                "word_input_preparation_runtime": word_input_runtime,
                "parse_preparation_runtime": parse_preparation_runtime,
                "document_parse_recovery_runtime": parse_recovery_runtime,
                "schema_session_runtime": schema_session_runtime,
                "extraction_graph_runtime": extraction_graph_runtime,
                "preflight_nonpdf_profile": preflight_nonpdf_profile,
                "resolve_nonpdf_budgets": resolve_nonpdf_budgets,
                "resolve_nonpdf_plan": resolve_nonpdf_plan,
                "apply_field_extract_timeout_floor": apply_field_extract_timeout_floor,
                "word_pdf_required": lambda: True,
                "is_word_file": is_word_file,
                "office_convert_enabled": office_convert_enabled,
                "docx_native_recovery_enabled": docx_native_recovery_enabled,
                "validate_word_preconditions": validate_word_preconditions,
                "resolve_conversion_timeout": resolve_conversion_timeout,
                "build_word_pdf_success": build_word_pdf_success,
                "resolve_word_pdf_failure": resolve_word_pdf_failure,
                "build_doc_to_docx_success": build_doc_to_docx_success,
                "build_doc_to_docx_failure": build_doc_to_docx_failure,
                "word_pdf_semaphore": word_pdf_semaphore,
                "ensure_preview_job_started": ensure_preview_job_started,
                "await_or_reuse_pdf": await_or_reuse_pdf,
                "run_with_progress_heartbeat": run_with_progress_heartbeat,
                "convert_doc_to_docx_with_timeout": convert_doc_to_docx_with_timeout,
                "tighten_parse_budgets_before_parse": tighten_parse_budgets_before_parse,
                "build_parse_session": build_parse_session,
                "build_parse_attempt_runner": build_parse_attempt_runner,
                "acquire_parse_execution_slots": acquire_parse_execution_slots,
                "run_parse_in_process_pool": run_parse_in_process_pool,
                "resolve_parse_progress_ramp_sec": resolve_parse_progress_ramp_sec,
                "unpack_parse_output": unpack_parse_output,
                "visual_parse_policy_runtime": visual_parse_policy_runtime,
                "parse_fallback_coordinator_runtime": parse_fallback_coordinator_runtime,
                "docx_native_recovery_runtime": docx_native_recovery_runtime,
                "fasttrack_fallback_runtime": fasttrack_fallback_runtime,
                "visual_chain_required": visual_chain_required,
                "visual_strict_mode": visual_strict_mode,
                "disable_fasttrack_fallback": disable_fasttrack_fallback,
                "extraction_llm_semaphore": extraction_llm_semaphore,
                "detect_domain_template": detect_domain_template,
                "extract_text_for_schema": extract_text_for_schema,
                "resolve_effective_schema": resolve_effective_schema,
                "resolve_dynamic_extract_timeout_sec": resolve_dynamic_extract_timeout_sec,
                "run_graph": run_graph,
                "resolve_extract_progress_ramp_sec": resolve_extract_progress_ramp_sec,
                "quick_extract_from_tables": quick_extract_from_tables,
                "disable_quick_table_fallback": disable_quick_table_fallback,
            }
        )
    runtime = DocumentPipelineRuntime(**runtime_kwargs)
    return (
        runtime,
        logger,
        input_plan_runtime,
        word_input_runtime,
        parse_preparation_runtime,
        parse_recovery_runtime,
        schema_session_runtime,
        extraction_graph_runtime,
    )


def test_document_pipeline_runtime_coordinates_mid_pipeline() -> None:
    (
        runtime,
        logger,
        input_plan_runtime,
        word_input_runtime,
        parse_preparation_runtime,
        parse_recovery_runtime,
        schema_session_runtime,
        extraction_graph_runtime,
    ) = _build_runtime()
    progress_events: list[tuple[str, float, str, dict[str, object]]] = []

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            requested_schema={"fields": {"amount": {"type": "number"}}},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress(
                progress_events, stage, ratio, message, extra
            ),
        )
    )

    assert outcome.parse_input_name == "demo.pdf"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "recovery-warning"
    assert outcome.parse_ms == 1250
    assert outcome.extract_ms == 234
    assert outcome.schema_meta == {"source": "auto", "naming_template": "finance_document"}
    assert outcome.dynamic_extract_timeout_meta == {"boost": True}
    assert outcome.final_state["results"] == {"amount": {"value": 100}}
    assert any(event[0] == "parsed" and event[1] == 0.76 for event in progress_events)
    assert input_plan_runtime.calls[0]["file_name"] == "demo.docx"
    assert word_input_runtime.calls[0]["parse_track"] == "FastTrack"
    assert parse_preparation_runtime.calls[0]["parse_input_name"] == "demo.pdf"
    assert parse_recovery_runtime.calls[0]["parse_source_file_name"] == "source.docx"
    assert schema_session_runtime.calls[0]["profile_hint"] == "mixed"
    assert extraction_graph_runtime.calls[0]["effective_schema_fields"] == {"amount": {"type": "number"}}
    assert len(logger.calls) == 3


def test_document_pipeline_runtime_routes_txt_to_direct_semantic_extract() -> None:
    direct_calls: list[dict[str, object]] = []

    class _StubDirectSemanticRuntime:
        @staticmethod
        def supports(file_name: str) -> bool:
            return file_name.lower().endswith(".txt")

        async def execute(self, **kwargs):
            direct_calls.append(dict(kwargs))
            return SimpleNamespace(
                marked_markdown="direct markdown",
                bbox_map={"txt_ref": [1.0]},
                table_blocks=[{"table_id": "semantic_t1", "source": "semantic"}],
                naming_template="text_document",
                schema_context_preview="direct preview",
                allow_schema_llm=False,
                effective_schema={"fields": {"地区生产总值": "number"}, "field_meta": {}},
                schema_meta={
                    "mode": "auto",
                    "source": "direct_text_semantic",
                    "route_kind": "direct_text_semantic",
                    "field_count": 1,
                    "fields": ["地区生产总值"],
                    "raw_fields": ["地区生产总值"],
                },
                effective_schema_fields={"地区生产总值": "number"},
                dynamic_extract_timeout_meta={"route_kind": "direct_text_semantic"},
                file_size_mb=0.01,
                final_state={
                    "results": {"地区生产总值": {"value": 123.4, "confidence": 0.91, "source_ref_id": None, "bbox": []}},
                    "errors": [],
                    "soft_warnings": ["direct_text_semantic_used"],
                },
                extract_ms=89,
                used_quick_fallback=False,
            )

    runtime, _, _, _, _, _, schema_session_runtime, extraction_graph_runtime = _build_runtime(
        direct_semantic_extract_runtime=_StubDirectSemanticRuntime(),
    )

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.txt",
            file_bytes=b"demo text",
            file_hash="hash123",
            requested_schema={},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
        )
    )

    assert schema_session_runtime.calls == []
    assert extraction_graph_runtime.calls == []
    assert direct_calls[0]["file_name"] == "demo.txt"
    assert direct_calls[0]["requested_schema"] == {}
    assert outcome.marked_markdown == "direct markdown"
    assert outcome.schema_meta["route_kind"] == "direct_text_semantic"
    assert outcome.allow_schema_llm is False
    assert outcome.final_state["results"]["地区生产总值"]["value"] == 123.4
    assert outcome.extract_ms == 89


def test_document_pipeline_runtime_raises_when_visual_chain_contract_fails() -> None:
    runtime, _, _, _, _, _, schema_session_runtime, extraction_graph_runtime = _build_runtime(
        build_visual_chain_contract=lambda **kwargs: {
            "required": True,
            "satisfied": False,
            "reasons": ["missing_visual_chain"],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            runtime.execute(
                file_name="demo.docx",
                file_bytes=b"docx",
                file_hash="hash123",
                requested_schema={},
                max_retries=1,
                initial_track="FastTrack",
                started_at_sec=50.0,
                emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
            )
        )

    assert exc_info.value.status_code == 503
    assert "missing_visual_chain" in str(exc_info.value.detail)
    assert schema_session_runtime.calls == []
    assert extraction_graph_runtime.calls == []


def test_document_pipeline_runtime_delegates_schema_and_graph_handoffs() -> None:
    schema_calls: list[dict[str, object]] = []
    graph_calls: list[dict[str, object]] = []

    class _StubSchemaRuntime:
        async def resolve(self, **kwargs):
            schema_calls.append(dict(kwargs))
            return SimpleNamespace(
                naming_template="delegated_template",
                schema_context_preview="delegated preview",
                allow_schema_llm=False,
                effective_schema={"fields": {"invoice_no": {"type": "string"}}},
                schema_meta={"source": "delegated", "naming_template": "delegated_template"},
                effective_schema_fields={"invoice_no": {"type": "string"}},
                extract_timeout_sec=222.0,
                dynamic_extract_timeout_meta={"delegated": True},
                file_size_mb=1.23,
            )

    class _StubGraphRuntime:
        async def execute(self, **kwargs):
            graph_calls.append(dict(kwargs))
            return SimpleNamespace(
                final_state={"results": {"invoice_no": {"value": "INV-001"}}, "errors": [], "soft_warnings": []},
                extract_ms=345,
                used_quick_fallback=True,
            )

    runtime, _, _, _, _, _, schema_session_runtime, extraction_graph_runtime = _build_runtime(
        document_pipeline_schema_runtime=_StubSchemaRuntime(),
        document_pipeline_graph_runtime=_StubGraphRuntime(),
    )

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            requested_schema={"fields": {"invoice_no": {"type": "string"}}},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
        )
    )

    assert schema_session_runtime.calls == []
    assert extraction_graph_runtime.calls == []
    assert schema_calls[0]["file_name"] == "demo.docx"
    assert schema_calls[0]["nonpdf_preflight"] == {"profile": "mixed"}
    assert graph_calls[0]["effective_schema_fields"] == {"invoice_no": {"type": "string"}}
    assert graph_calls[0]["extract_timeout_sec"] == 222.0
    assert outcome.naming_template == "delegated_template"
    assert outcome.dynamic_extract_timeout_meta == {"delegated": True}
    assert outcome.final_state["results"] == {"invoice_no": {"value": "INV-001"}}
    assert outcome.extract_ms == 345
    assert outcome.used_quick_fallback is True


def test_document_pipeline_runtime_delegates_parse_handoff() -> None:
    parse_calls: list[dict[str, object]] = []

    class _StubParseRuntime:
        async def execute(self, **kwargs):
            parse_calls.append(dict(kwargs))
            return SimpleNamespace(
                parse_timeout_sec=111.0,
                extract_timeout_sec=222.0,
                marked_markdown="delegated markdown",
                bbox_map={"delegated": [1.0]},
                table_blocks=[{"table_id": "delegated-t1"}],
                figure_blocks=[{"figure_id": "delegated-f1"}],
                parse_stats={"pipeline": "delegated"},
                parse_track="DelegatedTrack",
                parse_warning="delegated-warning",
                parse_ms=4321,
            )

    runtime, _, _, _, parse_preparation_runtime, parse_recovery_runtime, _, _ = _build_runtime(
        document_pipeline_parse_runtime=_StubParseRuntime(),
    )

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            requested_schema={"fields": {"amount": {"type": "number"}}},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
        )
    )

    assert parse_preparation_runtime.calls == []
    assert parse_recovery_runtime.calls == []
    assert parse_calls[0]["file_name"] == "demo.docx"
    assert parse_calls[0]["parse_input_name"] == "demo.pdf"
    assert parse_calls[0]["parse_started_at_sec"] == 100.0
    assert outcome.parse_track == "DelegatedTrack"
    assert outcome.parse_warning == "delegated-warning"
    assert outcome.parse_ms == 4321
    assert outcome.marked_markdown == "delegated markdown"


def test_document_pipeline_runtime_delegates_input_handoff() -> None:
    input_calls: list[dict[str, object]] = []

    class _StubInputRuntime:
        async def prepare(self, **kwargs):
            input_calls.append(dict(kwargs))
            return SimpleNamespace(
                parse_timeout_sec=123.0,
                extract_timeout_sec=234.0,
                nonpdf_preflight={"profile": "delegated"},
                nonpdf_budget={"parse_timeout_sec": 88.0},
                nonpdf_total_budget_sec=345.0,
                nonpdf_guard_sec=3.0,
                word_parse_extract_budget_sec=55.0,
                word_convert_budget_sec=22.0,
                word_parse_via_pdf=False,
                input_is_word=False,
                parse_input_name="delegated.pdf",
                parse_input_bytes=b"delegated",
                parse_track="DelegatedInputTrack",
                parse_warning="delegated-input-warning",
                conversion_diag={"delegated_input": True},
                word_suffix=".pdf",
            )

    runtime, _, input_plan_runtime, word_input_runtime, _, _, _, _ = _build_runtime(
        document_pipeline_input_runtime=_StubInputRuntime(),
    )

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            requested_schema={"fields": {"amount": {"type": "number"}}},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
        )
    )

    assert input_plan_runtime.calls == []
    assert word_input_runtime.calls == []
    assert input_calls[0]["file_name"] == "demo.docx"
    assert input_calls[0]["initial_track"] == "FastTrack"
    assert outcome.parse_input_name == "delegated.pdf"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "recovery-warning"


def test_document_pipeline_runtime_accepts_stage_dependency_bundles() -> None:
    (
        runtime,
        _logger,
        input_plan_runtime,
        word_input_runtime,
        parse_preparation_runtime,
        parse_recovery_runtime,
        schema_session_runtime,
        extraction_graph_runtime,
    ) = _build_runtime(use_dependency_bundles=True)

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            file_hash="hash123",
            requested_schema={"fields": {"amount": {"type": "number"}}},
            max_retries=2,
            initial_track="FastTrack",
            started_at_sec=50.0,
            emit_progress=lambda stage, ratio, message, extra=None: _record_progress([], stage, ratio, message, extra),
        )
    )

    assert input_plan_runtime.calls[0]["file_name"] == "demo.docx"
    assert word_input_runtime.calls[0]["parse_track"] == "FastTrack"
    assert parse_preparation_runtime.calls[0]["parse_input_name"] == "demo.pdf"
    assert parse_recovery_runtime.calls[0]["parse_source_file_name"] == "source.docx"
    assert schema_session_runtime.calls[0]["profile_hint"] == "mixed"
    assert extraction_graph_runtime.calls[0]["effective_schema_fields"] == {"amount": {"type": "number"}}
    assert outcome.parse_track == "VisualTrack"
