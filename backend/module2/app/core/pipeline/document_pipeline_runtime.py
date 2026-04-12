from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class DocumentPipelineInputBundle:
    document_input_plan_runtime: Any
    word_input_preparation_runtime: Any
    preflight_nonpdf_profile: Any
    resolve_nonpdf_budgets: Any
    resolve_nonpdf_plan: Any
    apply_field_extract_timeout_floor: Any
    word_pdf_required: Any
    is_word_file: Any
    office_convert_enabled: Any
    docx_native_recovery_enabled: Any
    validate_word_preconditions: Any
    resolve_conversion_timeout: Any
    build_word_pdf_success: Any
    resolve_word_pdf_failure: Any
    build_doc_to_docx_success: Any
    build_doc_to_docx_failure: Any
    word_pdf_semaphore: Any
    ensure_preview_job_started: Any
    await_or_reuse_pdf: Any
    run_with_progress_heartbeat: Any
    convert_doc_to_docx_with_timeout: Any


@dataclass(frozen=True)
class DocumentPipelineParseBundle:
    parse_preparation_runtime: Any
    document_parse_recovery_runtime: Any
    tighten_parse_budgets_before_parse: Any
    build_parse_session: Any
    build_parse_attempt_runner: Any
    acquire_parse_execution_slots: Any
    run_parse_in_process_pool: Any
    run_with_progress_heartbeat: Any
    resolve_parse_progress_ramp_sec: Any
    unpack_parse_output: Any
    visual_parse_policy_runtime: Any
    parse_fallback_coordinator_runtime: Any
    docx_native_recovery_runtime: Any
    fasttrack_fallback_runtime: Any
    is_word_file: Any
    visual_chain_required: Any
    docx_native_recovery_enabled: Any
    visual_strict_mode: Any
    disable_fasttrack_fallback: Any


@dataclass(frozen=True)
class DocumentPipelineSchemaBundle:
    schema_session_runtime: Any
    extraction_llm_semaphore: Any
    detect_domain_template: Any
    extract_text_for_schema: Any
    resolve_effective_schema: Any
    resolve_dynamic_extract_timeout_sec: Any
    is_word_file: Any


@dataclass(frozen=True)
class DocumentPipelineGraphBundle:
    extraction_graph_runtime: Any
    run_graph: Any
    extraction_llm_semaphore: Any
    run_with_progress_heartbeat: Any
    resolve_extract_progress_ramp_sec: Any
    quick_extract_from_tables: Any
    disable_quick_table_fallback: Any


@dataclass(frozen=True)
class DocumentInputPlanOutcome:
    parse_timeout_sec: float
    extract_timeout_sec: float
    nonpdf_preflight: Optional[Dict[str, Any]]
    nonpdf_budget: Optional[Dict[str, float]]
    nonpdf_total_budget_sec: Optional[float]
    nonpdf_guard_sec: float
    word_parse_extract_budget_sec: Optional[float]
    word_convert_budget_sec: Optional[float]
    word_parse_via_pdf: bool
    input_is_word: bool


class DocumentInputPlanRuntime:
    """Prepare top-level input/budget planning before conversion and parse orchestration begins."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    def build_plan(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        preflight_nonpdf_profile,
        resolve_nonpdf_budgets,
        resolve_nonpdf_plan,
        apply_field_extract_timeout_floor,
        word_pdf_required,
        is_word_file,
    ) -> DocumentInputPlanOutcome:
        parse_timeout_sec = max(5.0, float(self._getenv("MODULE2_PARSE_TIMEOUT_SEC", "150")))
        extract_timeout_sec = max(8.0, float(self._getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "150")))
        nonpdf_preflight: Optional[Dict[str, Any]] = None
        nonpdf_budget: Optional[Dict[str, float]] = None
        nonpdf_total_budget_sec: Optional[float] = None
        nonpdf_guard_sec = max(1.0, float(self._getenv("MODULE2_NONPDF_BUDGET_GUARD_SEC", "2.0")))
        word_parse_extract_budget_sec: Optional[float] = None
        word_convert_budget_sec: Optional[float] = None
        word_parse_via_pdf = bool(word_pdf_required())
        input_is_word = bool(is_word_file(file_name))

        if not file_name.lower().endswith(".pdf"):
            nonpdf_preflight = preflight_nonpdf_profile(file_name=file_name, file_bytes=file_bytes)
            nonpdf_budget = resolve_nonpdf_budgets(str(nonpdf_preflight.get("profile", "mixed")))
            nonpdf_plan = resolve_nonpdf_plan(
                file_name=file_name,
                parse_timeout_sec=float(nonpdf_budget["parse_timeout_sec"]),
                extract_timeout_sec=float(nonpdf_budget["extract_timeout_sec"]),
                nonpdf_total_budget_sec=float(nonpdf_budget.get("total_budget_sec", 90.0)),
                nonpdf_guard_sec=nonpdf_guard_sec,
                is_word_file=input_is_word,
            )
            parse_timeout_sec = nonpdf_plan.parse_timeout_sec
            extract_timeout_sec = nonpdf_plan.extract_timeout_sec
            nonpdf_total_budget_sec = nonpdf_plan.nonpdf_total_budget_sec
            word_parse_extract_budget_sec = nonpdf_plan.word_parse_extract_budget_sec
            word_convert_budget_sec = nonpdf_plan.word_convert_budget_sec

        extract_timeout_sec = apply_field_extract_timeout_floor(
            extract_timeout_sec=extract_timeout_sec,
        )
        return DocumentInputPlanOutcome(
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_preflight=nonpdf_preflight,
            nonpdf_budget=nonpdf_budget,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            word_parse_via_pdf=word_parse_via_pdf,
            input_is_word=input_is_word,
        )


class DocumentParseSessionRuntime:
    """Prepare parse-session timeout and progress context without touching I/O."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    def build_session(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        parse_input_name: str,
        parse_track: str,
        parse_timeout_sec: float,
        original_file_is_word: bool,
    ) -> Dict[str, Any]:
        resolved_parse_timeout_sec = float(parse_timeout_sec)
        parse_input_is_pdf = str(parse_input_name or "").lower().endswith(".pdf")
        if str(parse_track or "") == "VisualTrack" and parse_input_is_pdf:
            resolved_parse_timeout_sec = max(
                resolved_parse_timeout_sec,
                float(
                    self._getenv(
                        "MODULE2_PDF_VISUAL_PARSE_TIMEOUT_SEC",
                        self._getenv("MODULE2_MINERU_TIMEOUT_SEC", "900"),
                    )
                ),
            )

        parse_source_file_name = str(file_name or "") if original_file_is_word and parse_input_is_pdf else None
        parse_source_file_bytes = file_bytes if parse_source_file_name else None
        progress_message = (
            f"正在执行视觉解析：{parse_input_name}"
            "（MinerU 版面定位 -> ROI 裁剪 -> Gemini 图表理解）"
        )
        progress_extra = {
            "parse_input_name": str(parse_input_name or ""),
            "source_file_name": parse_source_file_name or "",
            "parse_track": str(parse_track or ""),
        }
        return {
            "parse_timeout_sec": resolved_parse_timeout_sec,
            "parse_source_file_name": parse_source_file_name,
            "parse_source_file_bytes": parse_source_file_bytes,
            "progress_message": progress_message,
            "progress_extra": progress_extra,
        }


@dataclass(frozen=True)
class DocumentPipelineInputOutcome:
    parse_timeout_sec: float
    extract_timeout_sec: float
    nonpdf_preflight: Optional[Dict[str, Any]]
    nonpdf_budget: Optional[Dict[str, Any]]
    nonpdf_total_budget_sec: Optional[float]
    nonpdf_guard_sec: float
    word_parse_extract_budget_sec: Optional[float]
    word_convert_budget_sec: Optional[float]
    word_parse_via_pdf: bool
    input_is_word: bool
    parse_input_name: str
    parse_input_bytes: bytes
    parse_track: str
    parse_warning: str
    conversion_diag: Dict[str, Any]
    word_suffix: str


class DocumentPipelineInputRuntime:
    """Resolve input-plan and Word-input preparation handoff details."""

    async def prepare(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        initial_track: str,
        started_at_sec: float,
        document_input_plan_runtime,
        preflight_nonpdf_profile,
        resolve_nonpdf_budgets,
        resolve_nonpdf_plan,
        apply_field_extract_timeout_floor,
        word_pdf_required,
        is_word_file,
        word_input_preparation_runtime,
        office_convert_enabled,
        docx_native_recovery_enabled,
        validate_word_preconditions,
        resolve_conversion_timeout,
        build_word_pdf_success,
        resolve_word_pdf_failure,
        build_doc_to_docx_success,
        build_doc_to_docx_failure,
        emit_progress,
        word_pdf_semaphore,
        ensure_preview_job_started,
        await_or_reuse_pdf,
        run_with_progress_heartbeat,
        convert_doc_to_docx_with_timeout,
    ) -> DocumentPipelineInputOutcome:
        document_input_plan = document_input_plan_runtime.build_plan(
            file_name=file_name,
            file_bytes=file_bytes,
            preflight_nonpdf_profile=preflight_nonpdf_profile,
            resolve_nonpdf_budgets=resolve_nonpdf_budgets,
            resolve_nonpdf_plan=resolve_nonpdf_plan,
            apply_field_extract_timeout_floor=apply_field_extract_timeout_floor,
            word_pdf_required=word_pdf_required,
            is_word_file=is_word_file,
        )
        parse_timeout_sec = document_input_plan.parse_timeout_sec
        extract_timeout_sec = document_input_plan.extract_timeout_sec
        nonpdf_preflight = document_input_plan.nonpdf_preflight
        nonpdf_budget = document_input_plan.nonpdf_budget
        nonpdf_total_budget_sec = document_input_plan.nonpdf_total_budget_sec
        nonpdf_guard_sec = document_input_plan.nonpdf_guard_sec
        word_parse_extract_budget_sec = document_input_plan.word_parse_extract_budget_sec
        word_convert_budget_sec = document_input_plan.word_convert_budget_sec
        word_parse_via_pdf = document_input_plan.word_parse_via_pdf
        input_is_word = document_input_plan.input_is_word

        word_input_preparation = await word_input_preparation_runtime.prepare(
            file_name=file_name,
            file_bytes=file_bytes,
            file_hash=file_hash,
            parse_track=str(initial_track or ""),
            parse_warning=None,
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            started_at_sec=started_at_sec,
            input_is_word=input_is_word,
            word_parse_via_pdf=word_parse_via_pdf,
            office_convert_enabled=office_convert_enabled(),
            docx_native_recovery_enabled=docx_native_recovery_enabled(),
            validate_preconditions=validate_word_preconditions,
            resolve_conversion_timeout=resolve_conversion_timeout,
            build_word_pdf_success=build_word_pdf_success,
            resolve_word_pdf_failure=resolve_word_pdf_failure,
            build_doc_to_docx_success=build_doc_to_docx_success,
            build_doc_to_docx_failure=build_doc_to_docx_failure,
            emit_progress=emit_progress,
            word_pdf_semaphore=word_pdf_semaphore,
            ensure_preview_job_started=ensure_preview_job_started,
            await_or_reuse_pdf=await_or_reuse_pdf,
            run_with_progress_heartbeat=run_with_progress_heartbeat,
            convert_doc_to_docx_with_timeout=convert_doc_to_docx_with_timeout,
        )

        return DocumentPipelineInputOutcome(
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_preflight=nonpdf_preflight,
            nonpdf_budget=nonpdf_budget,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            word_parse_via_pdf=word_parse_via_pdf,
            input_is_word=input_is_word,
            parse_input_name=word_input_preparation.parse_input_name,
            parse_input_bytes=word_input_preparation.parse_input_bytes,
            parse_track=word_input_preparation.parse_track,
            parse_warning=word_input_preparation.parse_warning,
            conversion_diag=word_input_preparation.conversion_diag,
            word_suffix=word_input_preparation.word_suffix,
        )


class DocumentParseAttemptRuntime:
    """Build parse-attempt runners and normalize subprocess parse output shapes."""

    def build_runner(
        self,
        *,
        loop: Any,
        acquire_parse_execution_slots,
        run_parse_in_process_pool,
        run_with_progress_heartbeat,
        emit_progress,
    ):
        async def _runner(**kwargs):
            return await self.run_parse_attempt(
                loop=loop,
                acquire_parse_execution_slots=acquire_parse_execution_slots,
                run_parse_in_process_pool=run_parse_in_process_pool,
                run_with_progress_heartbeat=run_with_progress_heartbeat,
                emit_progress=emit_progress,
                **kwargs,
            )

        return _runner

    @staticmethod
    def unpack_parse_output(
        parsed: Any,
    ) -> tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        if isinstance(parsed, tuple):
            if len(parsed) == 5:
                markdown, refs, tables, figures, extra_stats = parsed
                stats = extra_stats if isinstance(extra_stats, dict) else {}
                return markdown, refs, tables, figures if isinstance(figures, list) else [], stats
            if len(parsed) == 4:
                markdown, refs, tables, figures = parsed
                return markdown, refs, tables, figures if isinstance(figures, list) else [], {}
            if len(parsed) == 3:
                markdown, refs, tables = parsed
                return markdown, refs, tables, [], {}
        raise ValueError("Unexpected parse output shape")

    async def run_parse_attempt(
        self,
        *,
        loop: Any,
        attempt_file_bytes: bytes,
        attempt_file_name: str,
        attempt_track: str,
        attempt_timeout_sec: float,
        context_label: str,
        acquire_parse_execution_slots,
        run_parse_in_process_pool,
        run_with_progress_heartbeat,
        emit_progress,
        attempt_source_file_name: Optional[str] = None,
        attempt_source_file_bytes: Optional[bytes] = None,
        heartbeat_stage: str = "",
        heartbeat_base_ratio: float = 0.0,
        heartbeat_message: str = "",
        heartbeat_extra: Optional[Dict[str, Any]] = None,
        heartbeat_ceiling_ratio: Optional[float] = None,
        heartbeat_ramp_sec: Optional[float] = None,
    ) -> Any:
        async with acquire_parse_execution_slots(attempt_track):
            awaitable = run_parse_in_process_pool(
                loop=loop,
                file_bytes=attempt_file_bytes,
                file_name=attempt_file_name,
                track=attempt_track,
                timeout_sec=attempt_timeout_sec,
                context_label=context_label,
                source_file_name=attempt_source_file_name,
                source_file_bytes=attempt_source_file_bytes,
            )
            if heartbeat_stage:
                return await run_with_progress_heartbeat(
                    awaitable,
                    emit_progress=emit_progress,
                    stage=heartbeat_stage,
                    base_ratio=heartbeat_base_ratio,
                    ceiling_ratio=heartbeat_ceiling_ratio,
                    ramp_sec=heartbeat_ramp_sec,
                    message=heartbeat_message,
                    extra=heartbeat_extra,
                )
            return await awaitable


@dataclass(frozen=True)
class ParsePreparationOutcome:
    parse_timeout_sec: float
    extract_timeout_sec: float
    parse_warning: str
    parse_source_file_name: Optional[str]
    parse_source_file_bytes: Optional[bytes]
    progress_message: str
    progress_extra: Dict[str, Any]
    parse_attempt_runner: Any


class ParsePreparationRuntime:
    """Prepare parse-session budgets, progress payload, and parse-attempt runner wiring."""

    def __init__(self, *, perf_counter: Callable[[], float] = time.perf_counter) -> None:
        self._perf_counter = perf_counter

    async def prepare(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        parse_input_name: str,
        parse_track: str,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        parse_warning: Optional[str],
        nonpdf_total_budget_sec: Optional[float],
        started_at_sec: float,
        nonpdf_guard_sec: float,
        original_file_is_word: bool,
        tighten_parse_budgets_before_parse,
        build_session,
        emit_progress: Callable[[str, float, str, Dict[str, Any]], Awaitable[None]],
        build_runner,
        loop: Any,
        acquire_parse_execution_slots,
        run_parse_in_process_pool,
        run_with_progress_heartbeat,
    ) -> ParsePreparationOutcome:
        parse_budget_tighten = tighten_parse_budgets_before_parse(
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            elapsed_before_parse_sec=max(0.0, self._perf_counter() - started_at_sec),
            nonpdf_guard_sec=nonpdf_guard_sec,
        )
        resolved_parse_timeout_sec = parse_budget_tighten.parse_timeout_sec
        resolved_extract_timeout_sec = parse_budget_tighten.extract_timeout_sec
        resolved_parse_warning = str(parse_warning or "")
        if parse_budget_tighten.tightened:
            if resolved_parse_warning:
                resolved_parse_warning = f"{resolved_parse_warning}|{parse_budget_tighten.warning}"
            else:
                resolved_parse_warning = parse_budget_tighten.warning

        parse_session = build_session(
            file_name=file_name,
            file_bytes=file_bytes,
            parse_input_name=parse_input_name,
            parse_track=parse_track,
            parse_timeout_sec=resolved_parse_timeout_sec,
            original_file_is_word=original_file_is_word,
        )
        resolved_parse_timeout_sec = float(parse_session["parse_timeout_sec"] or resolved_parse_timeout_sec)
        progress_message = str(parse_session["progress_message"] or "")
        progress_extra = dict(parse_session["progress_extra"] or {})

        await emit_progress(
            "parsing",
            0.32,
            progress_message,
            progress_extra,
        )
        parse_attempt_runner = build_runner(
            loop=loop,
            acquire_parse_execution_slots=acquire_parse_execution_slots,
            run_parse_in_process_pool=run_parse_in_process_pool,
            run_with_progress_heartbeat=run_with_progress_heartbeat,
            emit_progress=emit_progress,
        )
        return ParsePreparationOutcome(
            parse_timeout_sec=resolved_parse_timeout_sec,
            extract_timeout_sec=resolved_extract_timeout_sec,
            parse_warning=resolved_parse_warning,
            parse_source_file_name=parse_session["parse_source_file_name"],
            parse_source_file_bytes=parse_session["parse_source_file_bytes"],
            progress_message=progress_message,
            progress_extra=progress_extra,
            parse_attempt_runner=parse_attempt_runner,
        )


@dataclass(frozen=True)
class DocumentPipelineParseOutcome:
    parse_timeout_sec: float
    extract_timeout_sec: float
    marked_markdown: str
    bbox_map: Dict[str, Any]
    table_blocks: List[Dict[str, Any]]
    figure_blocks: List[Dict[str, Any]]
    parse_stats: Dict[str, Any]
    parse_track: str
    parse_warning: str
    parse_ms: int


class DocumentPipelineParseRuntime:
    """Resolve parse-stage handoff details for the document pipeline."""

    def __init__(self, *, perf_counter: Callable[[], float] = time.perf_counter) -> None:
        self._perf_counter = perf_counter

    async def execute(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        parse_input_name: str,
        parse_input_bytes: bytes,
        parse_track: str,
        parse_warning: str,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: float | None,
        nonpdf_guard_sec: float,
        started_at_sec: float,
        parse_started_at_sec: float,
        input_is_word: bool,
        word_suffix: str,
        emit_progress,
        loop,
        parse_preparation_runtime,
        document_parse_recovery_runtime,
        tighten_parse_budgets_before_parse,
        build_parse_session,
        build_parse_attempt_runner,
        acquire_parse_execution_slots,
        run_parse_in_process_pool,
        run_with_progress_heartbeat,
        resolve_parse_progress_ramp_sec,
        unpack_parse_output,
        visual_parse_policy_runtime,
        parse_fallback_coordinator_runtime,
        docx_native_recovery_runtime,
        fasttrack_fallback_runtime,
        is_word_file,
        visual_chain_required,
        docx_native_recovery_enabled,
        visual_strict_mode,
        disable_fasttrack_fallback,
        logger,
    ) -> DocumentPipelineParseOutcome:
        parse_preparation = await parse_preparation_runtime.prepare(
            file_name=file_name,
            file_bytes=file_bytes,
            parse_input_name=parse_input_name,
            parse_track=parse_track,
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            parse_warning=parse_warning,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            started_at_sec=started_at_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            original_file_is_word=input_is_word,
            tighten_parse_budgets_before_parse=tighten_parse_budgets_before_parse,
            build_session=build_parse_session,
            emit_progress=emit_progress,
            build_runner=build_parse_attempt_runner,
            loop=loop,
            acquire_parse_execution_slots=acquire_parse_execution_slots,
            run_parse_in_process_pool=run_parse_in_process_pool,
            run_with_progress_heartbeat=run_with_progress_heartbeat,
        )
        resolved_parse_timeout_sec = parse_preparation.parse_timeout_sec
        resolved_extract_timeout_sec = parse_preparation.extract_timeout_sec
        resolved_parse_warning = parse_preparation.parse_warning

        parse_recovery_outcome = await document_parse_recovery_runtime.execute(
            file_name=file_name,
            file_bytes=file_bytes,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            parse_track=parse_track,
            parse_timeout_sec=resolved_parse_timeout_sec,
            parse_source_file_name=parse_preparation.parse_source_file_name,
            parse_source_file_bytes=parse_preparation.parse_source_file_bytes,
            progress_message=parse_preparation.progress_message,
            progress_extra=parse_preparation.progress_extra,
            resolve_parse_progress_ramp_sec=resolve_parse_progress_ramp_sec,
            parse_attempt_runner=parse_preparation.parse_attempt_runner,
            unpack_parse_output=unpack_parse_output,
            visual_parse_policy_runtime=visual_parse_policy_runtime,
            parse_fallback_coordinator_runtime=parse_fallback_coordinator_runtime,
            docx_native_recovery_runtime=docx_native_recovery_runtime,
            fasttrack_fallback_runtime=fasttrack_fallback_runtime,
            word_suffix=word_suffix,
            original_file_is_word=is_word_file(file_name),
            visual_chain_required=visual_chain_required(),
            docx_native_recovery_enabled=docx_native_recovery_enabled(),
            visual_strict=visual_strict_mode(),
            disable_fasttrack_fallback=disable_fasttrack_fallback(),
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            started_at_sec=started_at_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            current_parse_warning=resolved_parse_warning,
        )
        marked_markdown = parse_recovery_outcome.marked_markdown
        bbox_map = parse_recovery_outcome.bbox_map
        table_blocks = parse_recovery_outcome.table_blocks
        figure_blocks = parse_recovery_outcome.figure_blocks
        parse_stats = parse_recovery_outcome.parse_stats
        resolved_parse_track = parse_recovery_outcome.parse_track
        resolved_parse_warning = parse_recovery_outcome.parse_warning
        parse_ms = int((self._perf_counter() - parse_started_at_sec) * 1000)

        logger.info(
            "module2 parse finished file=%s parse_input=%s track=%s tables=%s figures=%s refs=%s parse_ms=%s",
            file_name,
            parse_input_name,
            resolved_parse_track,
            len(table_blocks),
            len(figure_blocks),
            len(bbox_map),
            parse_ms,
        )

        return DocumentPipelineParseOutcome(
            parse_timeout_sec=resolved_parse_timeout_sec,
            extract_timeout_sec=resolved_extract_timeout_sec,
            marked_markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            parse_stats=parse_stats,
            parse_track=resolved_parse_track,
            parse_warning=resolved_parse_warning,
            parse_ms=parse_ms,
        )


@dataclass(frozen=True)
class DocumentPipelineOutcome:
    parse_timeout_sec: float
    extract_timeout_sec: float
    nonpdf_preflight: Optional[Dict[str, Any]]
    nonpdf_budget: Optional[Dict[str, Any]]
    nonpdf_total_budget_sec: Optional[float]
    word_parse_extract_budget_sec: Optional[float]
    word_convert_budget_sec: Optional[float]
    word_parse_via_pdf: bool
    parse_input_name: str
    parse_input_bytes: bytes
    parse_track: str
    parse_warning: str
    conversion_diag: Dict[str, Any]
    parse_ms: int
    chain_contract: Dict[str, Any]
    marked_markdown: str
    bbox_map: Dict[str, Any]
    table_blocks: List[Dict[str, Any]]
    figure_blocks: List[Dict[str, Any]]
    parse_stats: Dict[str, Any]
    naming_template: str
    schema_context_preview: str
    allow_schema_llm: bool
    effective_schema: Dict[str, Any]
    schema_meta: Dict[str, Any]
    effective_schema_fields: Dict[str, Any]
    dynamic_extract_timeout_meta: Dict[str, Any]
    file_size_mb: float
    final_state: Dict[str, Any]
    extract_ms: int
    used_quick_fallback: bool


class DocumentPipelineFinalizeRuntime:
    """Finalize parse-chain contract checks and assemble the pipeline outcome."""

    def resolve_chain_contract(
        self,
        *,
        file_name: str,
        parse_input_name: str,
        parse_track: str,
        word_parse_via_pdf: bool,
        conversion_diag: Dict[str, Any],
        parse_stats: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        build_visual_chain_contract,
    ) -> Dict[str, Any]:
        chain_contract = build_visual_chain_contract(
            file_name=file_name,
            parse_input_name=parse_input_name,
            parse_track=parse_track,
            word_parse_via_pdf=word_parse_via_pdf,
            conversion_diag=conversion_diag,
            parse_stats=parse_stats,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
        )
        if chain_contract.get("required") and not chain_contract.get("satisfied"):
            reason_text = "; ".join(str(item) for item in (chain_contract.get("reasons") or [])[:8])
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Required visual chain contract failed for {file_name}: "
                    f"{reason_text or 'unknown_reason'}"
                ),
            )
        return chain_contract

    def build_outcome(
        self,
        *,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_preflight: Optional[Dict[str, Any]],
        nonpdf_budget: Optional[Dict[str, Any]],
        nonpdf_total_budget_sec: Optional[float],
        word_parse_extract_budget_sec: Optional[float],
        word_convert_budget_sec: Optional[float],
        word_parse_via_pdf: bool,
        parse_input_name: str,
        parse_input_bytes: bytes,
        parse_track: str,
        parse_warning: Optional[str],
        conversion_diag: Dict[str, Any],
        parse_ms: int,
        chain_contract: Dict[str, Any],
        marked_markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        parse_stats: Dict[str, Any],
        naming_template: str,
        schema_context_preview: str,
        allow_schema_llm: bool,
        effective_schema: Dict[str, Any],
        schema_meta: Dict[str, Any],
        effective_schema_fields: Dict[str, Any],
        dynamic_extract_timeout_meta: Dict[str, Any],
        file_size_mb: float,
        final_state: Dict[str, Any],
        extract_ms: int,
        used_quick_fallback: bool,
    ) -> DocumentPipelineOutcome:
        return DocumentPipelineOutcome(
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_preflight=nonpdf_preflight,
            nonpdf_budget=nonpdf_budget,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            word_parse_via_pdf=word_parse_via_pdf,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            parse_track=parse_track,
            parse_warning=str(parse_warning or ""),
            conversion_diag=conversion_diag,
            parse_ms=parse_ms,
            chain_contract=chain_contract,
            marked_markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            parse_stats=parse_stats,
            naming_template=naming_template,
            schema_context_preview=schema_context_preview,
            allow_schema_llm=allow_schema_llm,
            effective_schema=effective_schema,
            schema_meta=schema_meta,
            effective_schema_fields=effective_schema_fields,
            dynamic_extract_timeout_meta=dynamic_extract_timeout_meta,
            file_size_mb=file_size_mb,
            final_state=final_state,
            extract_ms=extract_ms,
            used_quick_fallback=used_quick_fallback,
        )


@dataclass(frozen=True)
class DocumentPipelineSchemaOutcome:
    naming_template: str
    schema_context_preview: str
    allow_schema_llm: bool
    effective_schema: Dict[str, Any]
    schema_meta: Dict[str, Any]
    effective_schema_fields: Dict[str, Any]
    extract_timeout_sec: float
    dynamic_extract_timeout_meta: Dict[str, Any]
    file_size_mb: float


class DocumentPipelineSchemaRuntime:
    """Resolve schema-session handoff details for the document pipeline."""

    async def resolve(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        marked_markdown: str,
        table_blocks,
        figure_blocks,
        requested_schema: Dict[str, Any],
        nonpdf_preflight,
        extract_timeout_sec: float,
        schema_session_runtime,
        extraction_llm_semaphore,
        detect_domain_template,
        extract_text_for_schema,
        resolve_effective_schema,
        resolve_dynamic_extract_timeout_sec,
        is_word_file,
        logger,
    ) -> DocumentPipelineSchemaOutcome:
        async with extraction_llm_semaphore:
            schema_session = await schema_session_runtime.resolve_session(
                file_name=file_name,
                file_bytes=file_bytes,
                markdown=marked_markdown,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
                requested_schema=requested_schema,
                profile_hint=str((nonpdf_preflight or {}).get("profile", "")),
                extract_timeout_sec=extract_timeout_sec,
                detect_domain_template=detect_domain_template,
                extract_text_for_schema=extract_text_for_schema,
                resolve_effective_schema=resolve_effective_schema,
                resolve_dynamic_extract_timeout_sec=resolve_dynamic_extract_timeout_sec,
                is_word_file=is_word_file,
            )

        naming_template = schema_session.naming_template
        schema_context_preview = schema_session.schema_context_preview
        allow_schema_llm = schema_session.allow_schema_llm
        effective_schema = schema_session.effective_schema
        schema_meta = schema_session.schema_meta
        effective_schema_fields = schema_session.effective_schema_fields
        resolved_extract_timeout_sec = schema_session.extract_timeout_sec
        dynamic_extract_timeout_meta = schema_session.dynamic_extract_timeout_meta
        file_size_mb = schema_session.file_size_mb

        logger.info(
            "module2 schema resolved file=%s source=%s field_count=%s template=%s",
            file_name,
            schema_meta.get("source", "unknown"),
            len(effective_schema_fields),
            schema_meta.get("naming_template", naming_template),
        )

        return DocumentPipelineSchemaOutcome(
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


@dataclass(frozen=True)
class DocumentPipelineGraphOutcome:
    final_state: Dict[str, Any]
    extract_ms: int
    used_quick_fallback: bool


class DocumentPipelineGraphRuntime:
    """Resolve extraction-graph handoff details for the document pipeline."""

    async def execute(
        self,
        *,
        file_name: str,
        marked_markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks,
        effective_schema: Dict[str, Any],
        effective_schema_fields: Dict[str, Any],
        figure_blocks,
        max_retries: int,
        extract_timeout_sec: float,
        schema_meta: Dict[str, Any],
        extraction_graph_runtime,
        run_graph,
        extraction_llm_semaphore,
        emit_progress,
        run_with_progress_heartbeat,
        resolve_extract_progress_ramp_sec,
        quick_extract_from_tables,
        disable_quick_table_fallback,
        logger,
    ) -> DocumentPipelineGraphOutcome:
        extraction_graph_outcome = await extraction_graph_runtime.execute(
            file_name=file_name,
            markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            effective_schema=effective_schema,
            effective_schema_fields=effective_schema_fields,
            figure_blocks=figure_blocks,
            max_retries=max_retries,
            extract_timeout_sec=extract_timeout_sec,
            schema_meta=schema_meta,
            run_graph=run_graph,
            extraction_llm_semaphore=extraction_llm_semaphore,
            emit_progress=emit_progress,
            run_with_progress_heartbeat=run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=resolve_extract_progress_ramp_sec,
            quick_extract_from_tables=quick_extract_from_tables,
            disable_quick_table_fallback=disable_quick_table_fallback,
        )
        final_state = extraction_graph_outcome.final_state
        extract_ms = extraction_graph_outcome.extract_ms
        used_quick_fallback = extraction_graph_outcome.used_quick_fallback

        logger.info(
            "module2 graph finished file=%s result_fields=%s errors=%s soft_warnings=%s extract_ms=%s",
            file_name,
            len(final_state.get("results", {}) if isinstance(final_state.get("results", {}), dict) else {}),
            len(final_state.get("errors", []) if isinstance(final_state.get("errors", []), list) else []),
            len(final_state.get("soft_warnings", []) if isinstance(final_state.get("soft_warnings", []), list) else []),
            extract_ms,
        )

        return DocumentPipelineGraphOutcome(
            final_state=final_state,
            extract_ms=extract_ms,
            used_quick_fallback=used_quick_fallback,
        )


class DocumentPipelineRuntime:
    """Coordinate the mid-pipeline orchestration between ingress and postprocess."""

    @staticmethod
    def _require_dependency(name: str, value: Any) -> Any:
        if value is None:
            raise ValueError(f"DocumentPipelineRuntime requires dependency '{name}'.")
        return value

    def __init__(
        self,
        *,
        document_input_plan_runtime: Any = None,
        word_input_preparation_runtime: Any = None,
        parse_preparation_runtime: Any = None,
        document_parse_recovery_runtime: Any = None,
        schema_session_runtime: Any = None,
        extraction_graph_runtime: Any = None,
        preflight_nonpdf_profile: Any = None,
        resolve_nonpdf_budgets: Any = None,
        resolve_nonpdf_plan: Any = None,
        apply_field_extract_timeout_floor: Any = None,
        word_pdf_required: Any = None,
        is_word_file: Any = None,
        office_convert_enabled: Any = None,
        docx_native_recovery_enabled: Any = None,
        validate_word_preconditions: Any = None,
        resolve_conversion_timeout: Any = None,
        build_word_pdf_success: Any = None,
        resolve_word_pdf_failure: Any = None,
        build_doc_to_docx_success: Any = None,
        build_doc_to_docx_failure: Any = None,
        word_pdf_semaphore: Any = None,
        ensure_preview_job_started: Any = None,
        await_or_reuse_pdf: Any = None,
        run_with_progress_heartbeat: Any = None,
        convert_doc_to_docx_with_timeout: Any = None,
        tighten_parse_budgets_before_parse: Any = None,
        build_parse_session: Any = None,
        build_parse_attempt_runner: Any = None,
        acquire_parse_execution_slots: Any = None,
        run_parse_in_process_pool: Any = None,
        resolve_parse_progress_ramp_sec: Any = None,
        unpack_parse_output: Any = None,
        visual_parse_policy_runtime: Any = None,
        parse_fallback_coordinator_runtime: Any = None,
        docx_native_recovery_runtime: Any = None,
        fasttrack_fallback_runtime: Any = None,
        visual_chain_required: Any = None,
        visual_strict_mode: Any = None,
        disable_fasttrack_fallback: Any = None,
        build_visual_chain_contract: Any = None,
        extraction_llm_semaphore: Any = None,
        detect_domain_template: Any = None,
        extract_text_for_schema: Any = None,
        resolve_effective_schema: Any = None,
        resolve_dynamic_extract_timeout_sec: Any = None,
        run_graph: Any = None,
        resolve_extract_progress_ramp_sec: Any = None,
        quick_extract_from_tables: Any = None,
        disable_quick_table_fallback: Any = None,
        xlsx_workbook_artifact_runtime: Any = None,
        logger: Any = None,
        input_bundle: DocumentPipelineInputBundle | None = None,
        parse_bundle: DocumentPipelineParseBundle | None = None,
        schema_bundle: DocumentPipelineSchemaBundle | None = None,
        graph_bundle: DocumentPipelineGraphBundle | None = None,
        document_pipeline_input_runtime: DocumentPipelineInputRuntime | None = None,
        document_pipeline_finalize_runtime: DocumentPipelineFinalizeRuntime | None = None,
        document_pipeline_parse_runtime: DocumentPipelineParseRuntime | None = None,
        document_pipeline_schema_runtime: DocumentPipelineSchemaRuntime | None = None,
        document_pipeline_graph_runtime: DocumentPipelineGraphRuntime | None = None,
        perf_counter: Callable[[], float] = time.perf_counter,
        parsed_progress_message: str = "版面解析完成，正在抽取字段与图表",
    ) -> None:
        self._input_bundle = input_bundle or DocumentPipelineInputBundle(
            document_input_plan_runtime=self._require_dependency(
                "document_input_plan_runtime",
                document_input_plan_runtime,
            ),
            word_input_preparation_runtime=self._require_dependency(
                "word_input_preparation_runtime",
                word_input_preparation_runtime,
            ),
            preflight_nonpdf_profile=self._require_dependency(
                "preflight_nonpdf_profile",
                preflight_nonpdf_profile,
            ),
            resolve_nonpdf_budgets=self._require_dependency("resolve_nonpdf_budgets", resolve_nonpdf_budgets),
            resolve_nonpdf_plan=self._require_dependency("resolve_nonpdf_plan", resolve_nonpdf_plan),
            apply_field_extract_timeout_floor=self._require_dependency(
                "apply_field_extract_timeout_floor",
                apply_field_extract_timeout_floor,
            ),
            word_pdf_required=self._require_dependency("word_pdf_required", word_pdf_required),
            is_word_file=self._require_dependency("is_word_file", is_word_file),
            office_convert_enabled=self._require_dependency("office_convert_enabled", office_convert_enabled),
            docx_native_recovery_enabled=self._require_dependency(
                "docx_native_recovery_enabled",
                docx_native_recovery_enabled,
            ),
            validate_word_preconditions=self._require_dependency(
                "validate_word_preconditions",
                validate_word_preconditions,
            ),
            resolve_conversion_timeout=self._require_dependency(
                "resolve_conversion_timeout",
                resolve_conversion_timeout,
            ),
            build_word_pdf_success=self._require_dependency("build_word_pdf_success", build_word_pdf_success),
            resolve_word_pdf_failure=self._require_dependency(
                "resolve_word_pdf_failure",
                resolve_word_pdf_failure,
            ),
            build_doc_to_docx_success=self._require_dependency(
                "build_doc_to_docx_success",
                build_doc_to_docx_success,
            ),
            build_doc_to_docx_failure=self._require_dependency(
                "build_doc_to_docx_failure",
                build_doc_to_docx_failure,
            ),
            word_pdf_semaphore=self._require_dependency("word_pdf_semaphore", word_pdf_semaphore),
            ensure_preview_job_started=self._require_dependency(
                "ensure_preview_job_started",
                ensure_preview_job_started,
            ),
            await_or_reuse_pdf=self._require_dependency("await_or_reuse_pdf", await_or_reuse_pdf),
            run_with_progress_heartbeat=self._require_dependency(
                "run_with_progress_heartbeat",
                run_with_progress_heartbeat,
            ),
            convert_doc_to_docx_with_timeout=self._require_dependency(
                "convert_doc_to_docx_with_timeout",
                convert_doc_to_docx_with_timeout,
            ),
        )
        self._parse_bundle = parse_bundle or DocumentPipelineParseBundle(
            parse_preparation_runtime=self._require_dependency(
                "parse_preparation_runtime",
                parse_preparation_runtime,
            ),
            document_parse_recovery_runtime=self._require_dependency(
                "document_parse_recovery_runtime",
                document_parse_recovery_runtime,
            ),
            tighten_parse_budgets_before_parse=self._require_dependency(
                "tighten_parse_budgets_before_parse",
                tighten_parse_budgets_before_parse,
            ),
            build_parse_session=self._require_dependency("build_parse_session", build_parse_session),
            build_parse_attempt_runner=self._require_dependency(
                "build_parse_attempt_runner",
                build_parse_attempt_runner,
            ),
            acquire_parse_execution_slots=self._require_dependency(
                "acquire_parse_execution_slots",
                acquire_parse_execution_slots,
            ),
            run_parse_in_process_pool=self._require_dependency(
                "run_parse_in_process_pool",
                run_parse_in_process_pool,
            ),
            run_with_progress_heartbeat=self._require_dependency(
                "run_with_progress_heartbeat",
                run_with_progress_heartbeat,
            ),
            resolve_parse_progress_ramp_sec=self._require_dependency(
                "resolve_parse_progress_ramp_sec",
                resolve_parse_progress_ramp_sec,
            ),
            unpack_parse_output=self._require_dependency("unpack_parse_output", unpack_parse_output),
            visual_parse_policy_runtime=self._require_dependency(
                "visual_parse_policy_runtime",
                visual_parse_policy_runtime,
            ),
            parse_fallback_coordinator_runtime=self._require_dependency(
                "parse_fallback_coordinator_runtime",
                parse_fallback_coordinator_runtime,
            ),
            docx_native_recovery_runtime=self._require_dependency(
                "docx_native_recovery_runtime",
                docx_native_recovery_runtime,
            ),
            fasttrack_fallback_runtime=self._require_dependency(
                "fasttrack_fallback_runtime",
                fasttrack_fallback_runtime,
            ),
            is_word_file=self._require_dependency("is_word_file", is_word_file),
            visual_chain_required=self._require_dependency("visual_chain_required", visual_chain_required),
            docx_native_recovery_enabled=self._require_dependency(
                "docx_native_recovery_enabled",
                docx_native_recovery_enabled,
            ),
            visual_strict_mode=self._require_dependency("visual_strict_mode", visual_strict_mode),
            disable_fasttrack_fallback=self._require_dependency(
                "disable_fasttrack_fallback",
                disable_fasttrack_fallback,
            ),
        )
        self._schema_bundle = schema_bundle or DocumentPipelineSchemaBundle(
            schema_session_runtime=self._require_dependency("schema_session_runtime", schema_session_runtime),
            extraction_llm_semaphore=self._require_dependency(
                "extraction_llm_semaphore",
                extraction_llm_semaphore,
            ),
            detect_domain_template=self._require_dependency(
                "detect_domain_template",
                detect_domain_template,
            ),
            extract_text_for_schema=self._require_dependency("extract_text_for_schema", extract_text_for_schema),
            resolve_effective_schema=self._require_dependency(
                "resolve_effective_schema",
                resolve_effective_schema,
            ),
            resolve_dynamic_extract_timeout_sec=self._require_dependency(
                "resolve_dynamic_extract_timeout_sec",
                resolve_dynamic_extract_timeout_sec,
            ),
            is_word_file=self._require_dependency("is_word_file", is_word_file),
        )
        self._graph_bundle = graph_bundle or DocumentPipelineGraphBundle(
            extraction_graph_runtime=self._require_dependency(
                "extraction_graph_runtime",
                extraction_graph_runtime,
            ),
            run_graph=self._require_dependency("run_graph", run_graph),
            extraction_llm_semaphore=self._require_dependency(
                "extraction_llm_semaphore",
                extraction_llm_semaphore,
            ),
            run_with_progress_heartbeat=self._require_dependency(
                "run_with_progress_heartbeat",
                run_with_progress_heartbeat,
            ),
            resolve_extract_progress_ramp_sec=self._require_dependency(
                "resolve_extract_progress_ramp_sec",
                resolve_extract_progress_ramp_sec,
            ),
            quick_extract_from_tables=self._require_dependency(
                "quick_extract_from_tables",
                quick_extract_from_tables,
            ),
            disable_quick_table_fallback=self._require_dependency(
                "disable_quick_table_fallback",
                disable_quick_table_fallback,
            ),
        )
        self._build_visual_chain_contract = self._require_dependency(
            "build_visual_chain_contract",
            build_visual_chain_contract,
        )
        self._xlsx_workbook_artifact_runtime = xlsx_workbook_artifact_runtime
        self._logger = self._require_dependency("logger", logger)
        self._document_pipeline_input_runtime = document_pipeline_input_runtime or DocumentPipelineInputRuntime()
        self._document_pipeline_finalize_runtime = (
            document_pipeline_finalize_runtime or DocumentPipelineFinalizeRuntime()
        )
        self._document_pipeline_parse_runtime = document_pipeline_parse_runtime or DocumentPipelineParseRuntime(
            perf_counter=perf_counter
        )
        self._document_pipeline_schema_runtime = document_pipeline_schema_runtime or DocumentPipelineSchemaRuntime()
        self._document_pipeline_graph_runtime = document_pipeline_graph_runtime or DocumentPipelineGraphRuntime()
        self._perf_counter = perf_counter
        self._parsed_progress_message = parsed_progress_message

    async def execute(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        requested_schema: Dict[str, Any],
        max_retries: int,
        initial_track: str,
        started_at_sec: float,
        emit_progress,
    ) -> DocumentPipelineOutcome:
        input_bundle = self._input_bundle
        parse_bundle = self._parse_bundle
        schema_bundle = self._schema_bundle
        graph_bundle = self._graph_bundle

        loop = asyncio.get_running_loop()
        parse_t0 = self._perf_counter()
        input_stage = await self._document_pipeline_input_runtime.prepare(
            file_name=file_name,
            file_bytes=file_bytes,
            file_hash=file_hash,
            initial_track=initial_track,
            started_at_sec=started_at_sec,
            document_input_plan_runtime=input_bundle.document_input_plan_runtime,
            preflight_nonpdf_profile=input_bundle.preflight_nonpdf_profile,
            resolve_nonpdf_budgets=input_bundle.resolve_nonpdf_budgets,
            resolve_nonpdf_plan=input_bundle.resolve_nonpdf_plan,
            apply_field_extract_timeout_floor=input_bundle.apply_field_extract_timeout_floor,
            word_pdf_required=input_bundle.word_pdf_required,
            is_word_file=input_bundle.is_word_file,
            word_input_preparation_runtime=input_bundle.word_input_preparation_runtime,
            office_convert_enabled=input_bundle.office_convert_enabled,
            docx_native_recovery_enabled=input_bundle.docx_native_recovery_enabled,
            validate_word_preconditions=input_bundle.validate_word_preconditions,
            resolve_conversion_timeout=input_bundle.resolve_conversion_timeout,
            build_word_pdf_success=input_bundle.build_word_pdf_success,
            resolve_word_pdf_failure=input_bundle.resolve_word_pdf_failure,
            build_doc_to_docx_success=input_bundle.build_doc_to_docx_success,
            build_doc_to_docx_failure=input_bundle.build_doc_to_docx_failure,
            emit_progress=emit_progress,
            word_pdf_semaphore=input_bundle.word_pdf_semaphore,
            ensure_preview_job_started=input_bundle.ensure_preview_job_started,
            await_or_reuse_pdf=input_bundle.await_or_reuse_pdf,
            run_with_progress_heartbeat=input_bundle.run_with_progress_heartbeat,
            convert_doc_to_docx_with_timeout=input_bundle.convert_doc_to_docx_with_timeout,
        )
        parse_timeout_sec = input_stage.parse_timeout_sec
        extract_timeout_sec = input_stage.extract_timeout_sec
        nonpdf_preflight = input_stage.nonpdf_preflight
        nonpdf_budget = input_stage.nonpdf_budget
        nonpdf_total_budget_sec = input_stage.nonpdf_total_budget_sec
        nonpdf_guard_sec = input_stage.nonpdf_guard_sec
        word_parse_extract_budget_sec = input_stage.word_parse_extract_budget_sec
        word_convert_budget_sec = input_stage.word_convert_budget_sec
        word_parse_via_pdf = input_stage.word_parse_via_pdf
        input_is_word = input_stage.input_is_word
        parse_input_name = input_stage.parse_input_name
        parse_input_bytes = input_stage.parse_input_bytes
        parse_track = input_stage.parse_track
        parse_warning = input_stage.parse_warning
        conversion_diag = input_stage.conversion_diag
        word_suffix = input_stage.word_suffix

        parse_stage = await self._document_pipeline_parse_runtime.execute(
            file_name=file_name,
            file_bytes=file_bytes,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            parse_track=parse_track,
            parse_warning=str(parse_warning or ""),
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
            started_at_sec=started_at_sec,
            parse_started_at_sec=parse_t0,
            input_is_word=input_is_word,
            word_suffix=word_suffix,
            emit_progress=emit_progress,
            loop=loop,
            parse_preparation_runtime=parse_bundle.parse_preparation_runtime,
            document_parse_recovery_runtime=parse_bundle.document_parse_recovery_runtime,
            tighten_parse_budgets_before_parse=parse_bundle.tighten_parse_budgets_before_parse,
            build_parse_session=parse_bundle.build_parse_session,
            build_parse_attempt_runner=parse_bundle.build_parse_attempt_runner,
            acquire_parse_execution_slots=parse_bundle.acquire_parse_execution_slots,
            run_parse_in_process_pool=parse_bundle.run_parse_in_process_pool,
            run_with_progress_heartbeat=parse_bundle.run_with_progress_heartbeat,
            resolve_parse_progress_ramp_sec=parse_bundle.resolve_parse_progress_ramp_sec,
            unpack_parse_output=parse_bundle.unpack_parse_output,
            visual_parse_policy_runtime=parse_bundle.visual_parse_policy_runtime,
            parse_fallback_coordinator_runtime=parse_bundle.parse_fallback_coordinator_runtime,
            docx_native_recovery_runtime=parse_bundle.docx_native_recovery_runtime,
            fasttrack_fallback_runtime=parse_bundle.fasttrack_fallback_runtime,
            is_word_file=parse_bundle.is_word_file,
            visual_chain_required=parse_bundle.visual_chain_required,
            docx_native_recovery_enabled=parse_bundle.docx_native_recovery_enabled,
            visual_strict_mode=parse_bundle.visual_strict_mode,
            disable_fasttrack_fallback=parse_bundle.disable_fasttrack_fallback,
            logger=self._logger,
        )
        parse_timeout_sec = parse_stage.parse_timeout_sec
        extract_timeout_sec = parse_stage.extract_timeout_sec
        marked_markdown = parse_stage.marked_markdown
        bbox_map = parse_stage.bbox_map
        table_blocks = parse_stage.table_blocks
        figure_blocks = parse_stage.figure_blocks
        parse_stats = parse_stage.parse_stats
        parse_track = parse_stage.parse_track
        parse_warning = parse_stage.parse_warning
        parse_ms = parse_stage.parse_ms

        if self._xlsx_workbook_artifact_runtime is not None:
            try:
                table_blocks, parse_stats = self._xlsx_workbook_artifact_runtime.build_artifacts_for_pipeline(
                    file_name=file_name,
                    file_hash=file_hash,
                    file_bytes=file_bytes,
                    table_blocks=table_blocks,
                    parse_stats=parse_stats,
                )
            except Exception as exc:
                self._logger.warning(
                    "module2 xlsx workbook artifact build failed file=%s error=%s: %s",
                    file_name,
                    type(exc).__name__,
                    exc,
                )

        chain_contract = self._document_pipeline_finalize_runtime.resolve_chain_contract(
            file_name=file_name,
            parse_input_name=parse_input_name,
            parse_track=parse_track,
            word_parse_via_pdf=word_parse_via_pdf,
            conversion_diag=conversion_diag,
            parse_stats=parse_stats,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            build_visual_chain_contract=self._build_visual_chain_contract,
        )
        await emit_progress("parsed", 0.76, self._parsed_progress_message)

        schema_session = await self._document_pipeline_schema_runtime.resolve(
            file_name=file_name,
            file_bytes=file_bytes,
            marked_markdown=marked_markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            requested_schema=requested_schema,
            nonpdf_preflight=nonpdf_preflight,
            extract_timeout_sec=extract_timeout_sec,
            schema_session_runtime=schema_bundle.schema_session_runtime,
            extraction_llm_semaphore=schema_bundle.extraction_llm_semaphore,
            detect_domain_template=schema_bundle.detect_domain_template,
            extract_text_for_schema=schema_bundle.extract_text_for_schema,
            resolve_effective_schema=schema_bundle.resolve_effective_schema,
            resolve_dynamic_extract_timeout_sec=schema_bundle.resolve_dynamic_extract_timeout_sec,
            is_word_file=schema_bundle.is_word_file,
            logger=self._logger,
        )
        naming_template = schema_session.naming_template
        schema_context_preview = schema_session.schema_context_preview
        allow_schema_llm = schema_session.allow_schema_llm
        effective_schema = schema_session.effective_schema
        schema_meta = schema_session.schema_meta
        effective_schema_fields = schema_session.effective_schema_fields
        extract_timeout_sec = schema_session.extract_timeout_sec
        dynamic_extract_timeout_meta = schema_session.dynamic_extract_timeout_meta
        file_size_mb = schema_session.file_size_mb

        extraction_graph_outcome = await self._document_pipeline_graph_runtime.execute(
            file_name=file_name,
            marked_markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            effective_schema=effective_schema,
            effective_schema_fields=effective_schema_fields,
            figure_blocks=figure_blocks,
            max_retries=max_retries,
            extract_timeout_sec=extract_timeout_sec,
            schema_meta=schema_meta,
            extraction_graph_runtime=graph_bundle.extraction_graph_runtime,
            run_graph=graph_bundle.run_graph,
            extraction_llm_semaphore=graph_bundle.extraction_llm_semaphore,
            emit_progress=emit_progress,
            run_with_progress_heartbeat=graph_bundle.run_with_progress_heartbeat,
            resolve_extract_progress_ramp_sec=graph_bundle.resolve_extract_progress_ramp_sec,
            quick_extract_from_tables=graph_bundle.quick_extract_from_tables,
            disable_quick_table_fallback=graph_bundle.disable_quick_table_fallback,
            logger=self._logger,
        )
        final_state = extraction_graph_outcome.final_state
        extract_ms = extraction_graph_outcome.extract_ms
        used_quick_fallback = extraction_graph_outcome.used_quick_fallback

        return self._document_pipeline_finalize_runtime.build_outcome(
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_preflight=nonpdf_preflight,
            nonpdf_budget=nonpdf_budget,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            word_parse_via_pdf=word_parse_via_pdf,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            parse_track=parse_track,
            parse_warning=str(parse_warning or ""),
            conversion_diag=conversion_diag,
            parse_ms=parse_ms,
            chain_contract=chain_contract,
            marked_markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            parse_stats=parse_stats,
            naming_template=naming_template,
            schema_context_preview=schema_context_preview,
            allow_schema_llm=allow_schema_llm,
            effective_schema=effective_schema,
            schema_meta=schema_meta,
            effective_schema_fields=effective_schema_fields,
            dynamic_extract_timeout_meta=dynamic_extract_timeout_meta,
            file_size_mb=file_size_mb,
            final_state=final_state,
            extract_ms=extract_ms,
            used_quick_fallback=used_quick_fallback,
        )
