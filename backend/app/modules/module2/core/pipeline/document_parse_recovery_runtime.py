from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class VisualParseFailureProfile:
    message: str
    lower_message: str
    visual_backend_missing: bool
    visual_pipeline_unusable: bool
    unsupported_file_type: bool
    backend_unavailable: bool


@dataclass(frozen=True)
class VisualTimeoutFallbackDecision:
    native_timeout_detail: str
    terminal_status_code: Optional[int] = None
    terminal_detail: str = ""
    try_docx_native_recovery: bool = False
    docx_native_recovery_reason: str = ""
    fallback_timeout_sec: Optional[float] = None
    fallback_track: str = ""
    fallback_hint: str = ""
    fallback_context_label: str = ""

    @property
    def should_attempt_fasttrack_fallback(self) -> bool:
        return self.fallback_timeout_sec is not None and bool(self.fallback_track)


@dataclass(frozen=True)
class VisualExceptionFallbackDecision:
    terminal_status_code: Optional[int] = None
    terminal_detail: str = ""
    try_docx_native_recovery: bool = False
    docx_native_recovery_reason: str = ""
    fallback_warning: str = ""
    fallback_track: str = ""
    fallback_context_label: str = ""

    @property
    def should_attempt_fasttrack_fallback(self) -> bool:
        return bool(self.fallback_warning) and bool(self.fallback_track)


class FastTrackFallbackRuntime:
    """Run FastTrack fallback attempts and normalize fallback error mapping."""

    async def run_fasttrack_fallback(
        self,
        *,
        file_name: str,
        parse_input_name: str,
        parse_input_bytes: bytes,
        fallback_timeout_sec: float,
        fallback_context_label: str,
        parse_attempt,
        unpack_parse_output,
        native_timeout_detail: Optional[str] = None,
        parse_source_file_name: Optional[str] = None,
        parse_source_file_bytes: Optional[bytes] = None,
    ) -> tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        timeout_detail = str(native_timeout_detail or "").strip() or f"Native parsing timed out for {file_name}"
        try:
            parsed_output = await parse_attempt(
                attempt_file_bytes=parse_input_bytes,
                attempt_file_name=parse_input_name,
                attempt_track="FastTrack",
                attempt_timeout_sec=float(fallback_timeout_sec),
                context_label=fallback_context_label,
                attempt_source_file_name=parse_source_file_name,
                attempt_source_file_bytes=parse_source_file_bytes,
            )
            return unpack_parse_output(parsed_output)
        except TimeoutError as fallback_exc:
            raise HTTPException(status_code=504, detail=timeout_detail) from fallback_exc
        except Exception as fallback_exc:
            fallback_message = str(fallback_exc)
            if "Unsupported file type" in fallback_message:
                raise HTTPException(status_code=400, detail=fallback_message) from fallback_exc
            raise HTTPException(
                status_code=500,
                detail=f"Native parsing failed for {file_name}: {fallback_exc}",
            ) from fallback_exc


@dataclass(frozen=True)
class ParseFallbackOutcome:
    result: Optional[tuple[Any, Any, Any, Any, Any]] = None
    parse_track: str = ""
    parse_warning: str = ""

    @property
    def resolved(self) -> bool:
        return self.result is not None


class ParseFallbackCoordinatorRuntime:
    """Coordinate docx recovery / FastTrack fallback bookkeeping around existing runtimes."""

    async def try_docx_native_recovery(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reason: str,
        enabled: bool,
        current_warning: Optional[str],
        success_track: str,
        success_warning: str,
        append_warning,
        docx_native_recovery_runtime,
        parse_attempt_runner,
        unpack_parse_output,
        timeout_hint_sec: Optional[float] = None,
        nonpdf_total_budget_sec: Optional[float] = None,
        elapsed_sec: float = 0.0,
        nonpdf_guard_sec: float = 0.0,
    ) -> ParseFallbackOutcome:
        try:
            recovery = await docx_native_recovery_runtime.try_recover(
                file_name=file_name,
                file_bytes=file_bytes,
                reason=reason,
                enabled=enabled,
                parse_attempt=parse_attempt_runner,
                unpack_parse_output=unpack_parse_output,
                timeout_hint_sec=timeout_hint_sec,
                nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                elapsed_sec=elapsed_sec,
                nonpdf_guard_sec=nonpdf_guard_sec,
            )
        except Exception as recovery_exc:
            return ParseFallbackOutcome(
                parse_warning=append_warning(
                    current_warning,
                    f"docx_native_recovery_failed:{type(recovery_exc).__name__}",
                )
            )

        if recovery is None:
            return ParseFallbackOutcome(parse_warning=str(current_warning or ""))

        return ParseFallbackOutcome(
            result=recovery,
            parse_track=success_track,
            parse_warning=append_warning(current_warning, success_warning),
        )

    async def run_fasttrack_fallback(
        self,
        *,
        file_name: str,
        parse_input_name: str,
        parse_input_bytes: bytes,
        fallback_timeout_sec: float,
        fallback_context_label: str,
        current_warning: Optional[str],
        success_track: str,
        success_warning: str,
        append_warning,
        fasttrack_fallback_runtime,
        parse_attempt_runner,
        unpack_parse_output,
        native_timeout_detail: Optional[str] = None,
        parse_source_file_name: Optional[str] = None,
        parse_source_file_bytes: Optional[bytes] = None,
    ) -> ParseFallbackOutcome:
        result = await fasttrack_fallback_runtime.run_fasttrack_fallback(
            file_name=file_name,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            fallback_timeout_sec=fallback_timeout_sec,
            fallback_context_label=fallback_context_label,
            parse_attempt=parse_attempt_runner,
            unpack_parse_output=unpack_parse_output,
            native_timeout_detail=native_timeout_detail,
            parse_source_file_name=parse_source_file_name,
            parse_source_file_bytes=parse_source_file_bytes,
        )
        return ParseFallbackOutcome(
            result=result,
            parse_track=success_track,
            parse_warning=append_warning(current_warning, success_warning),
        )


class VisualParsePolicyRuntime:
    """Resolve visual-parse timeout/error fallback policy without touching I/O."""

    @staticmethod
    def append_warning(current_warning: Optional[str], warning: str) -> str:
        warning_fragment = str(warning or "").strip()
        if not warning_fragment:
            return str(current_warning or "").strip()
        current_fragment = str(current_warning or "").strip()
        if not current_fragment:
            return warning_fragment
        return f"{current_fragment}|{warning_fragment}"

    @staticmethod
    def classify_exception(message: str) -> VisualParseFailureProfile:
        normalized_message = str(message or "")
        lower_message = normalized_message.lower()
        return VisualParseFailureProfile(
            message=normalized_message,
            lower_message=lower_message,
            visual_backend_missing=(
                ("VisualTrack OCR backend is unavailable" in normalized_message)
                or ("rapidocr_onnxruntime" in lower_message)
                or ("pymupdf" in lower_message)
            ),
            visual_pipeline_unusable=(
                "visual-first pipeline returned no usable result" in lower_message
                or ("mineru" in lower_message and ("failed" in lower_message or "not found" in lower_message))
            ),
            unsupported_file_type="Unsupported file type" in normalized_message,
            backend_unavailable=("backend is unavailable" in lower_message) or ("please install" in lower_message),
        )

    @staticmethod
    def resolve_timeout_fallback(
        *,
        file_name: str,
        parse_track: str,
        parse_input_name: str,
        original_file_is_word: bool,
        word_suffix: str,
        parse_timeout_sec: float,
        visual_chain_required: bool,
        nonpdf_total_budget_sec: Optional[float],
        elapsed_sec: float,
        nonpdf_guard_sec: float,
    ) -> VisualTimeoutFallbackDecision:
        native_timeout_detail = f"Native parsing timed out for {file_name}"
        parse_input_is_pdf = str(parse_input_name or "").lower().endswith(".pdf")
        if parse_input_is_pdf and visual_chain_required:
            return VisualTimeoutFallbackDecision(
                native_timeout_detail=native_timeout_detail,
                terminal_status_code=504,
                terminal_detail=(
                    f"Required visual PDF chain timed out for {file_name}. "
                    "FastTrack/native fallback is disabled."
                ),
            )

        is_word_pdf_parse = bool(original_file_is_word) and parse_input_is_pdf
        should_try_pdf_native_fallback = str(parse_track or "") == "VisualTrack" and parse_input_is_pdf
        if not (is_word_pdf_parse or should_try_pdf_native_fallback):
            return VisualTimeoutFallbackDecision(
                native_timeout_detail=native_timeout_detail,
                terminal_status_code=504,
                terminal_detail=native_timeout_detail,
            )

        if is_word_pdf_parse:
            fallback_timeout_sec = max(20.0, min(120.0, float(parse_timeout_sec) * 1.15))
            fallback_track = "VisualTrack->WordPdfFastTrackFallback"
            fallback_hint = "word_pdf_parse_timeout_fallback_fasttrack"
        else:
            fallback_timeout_sec = max(20.0, min(120.0, float(parse_timeout_sec)))
            fallback_track = "VisualTrack->FastTrackTimeoutFallback"
            fallback_hint = "pdf_visual_timeout_fallback_fasttrack"

        if nonpdf_total_budget_sec is not None:
            remaining_budget = float(nonpdf_total_budget_sec) - max(0.0, float(elapsed_sec)) - max(6.0, float(nonpdf_guard_sec))
            if remaining_budget <= 6.0:
                return VisualTimeoutFallbackDecision(
                    native_timeout_detail=native_timeout_detail,
                    terminal_status_code=504,
                    terminal_detail=native_timeout_detail,
                )
            fallback_timeout_sec = min(fallback_timeout_sec, max(6.0, remaining_budget))

        return VisualTimeoutFallbackDecision(
            native_timeout_detail=native_timeout_detail,
            try_docx_native_recovery=is_word_pdf_parse and str(word_suffix or "").lower() == ".docx",
            docx_native_recovery_reason="word_pdf_parse_timeout" if is_word_pdf_parse else "",
            fallback_timeout_sec=fallback_timeout_sec,
            fallback_track=fallback_track,
            fallback_hint=fallback_hint,
            fallback_context_label=f"{file_name}:FastTrackTimeoutFallback",
        )

    def resolve_exception_fallback(
        self,
        *,
        file_name: str,
        parse_track: str,
        parse_input_name: str,
        word_suffix: str,
        message: str,
        visual_chain_required: bool,
        visual_strict: bool,
        disable_fasttrack_fallback: bool,
    ) -> VisualExceptionFallbackDecision:
        profile = self.classify_exception(message)
        is_visual_pdf = str(parse_track or "") == "VisualTrack" and str(parse_input_name or "").lower().endswith(".pdf")

        if is_visual_pdf and visual_chain_required:
            if profile.visual_backend_missing:
                return VisualExceptionFallbackDecision(
                    terminal_status_code=503,
                    terminal_detail=(
                        "Required visual PDF chain is unavailable: OCR/MinerU dependencies are not ready. "
                        "FastTrack/native fallback is disabled."
                    ),
                )
            if profile.visual_pipeline_unusable:
                return VisualExceptionFallbackDecision(
                    terminal_status_code=503,
                    terminal_detail=(
                        "Required visual PDF chain failed: MinerU did not return a usable visual-first result. "
                        "FastTrack/native fallback is disabled."
                    ),
                )

        try_docx_native_recovery = (
            is_visual_pdf
            and str(word_suffix or "").lower() == ".docx"
            and (profile.visual_backend_missing or profile.visual_pipeline_unusable)
        )

        if is_visual_pdf:
            fallback_warning = ""
            terminal_status_code: Optional[int] = None
            terminal_detail = ""

            if profile.visual_backend_missing and not visual_strict:
                fallback_warning = "VisualTrack OCR backend unavailable, auto-fallback to native FastTrack parsing."
            elif profile.visual_pipeline_unusable and not visual_strict:
                fallback_warning = "VisualTrack/MinerU returned no usable layout, auto-fallback to native FastTrack parsing."
            elif profile.visual_backend_missing and visual_strict:
                terminal_status_code = 503
                terminal_detail = (
                    "VisualTrack OCR backend unavailable and strict mode is enabled. "
                    "Please install pymupdf/rapidocr-onnxruntime or disable MODULE2_VISUAL_STRICT."
                )
            elif visual_strict and profile.visual_pipeline_unusable:
                terminal_status_code = 503
                terminal_detail = (
                    "VisualTrack/MinerU parsing failed in strict mode. "
                    "Please verify MinerU runtime and Vision configuration before retrying."
                )
            elif profile.unsupported_file_type:
                terminal_status_code = 400
                terminal_detail = profile.message
            elif profile.backend_unavailable:
                terminal_status_code = 503
                terminal_detail = profile.message
            else:
                terminal_status_code = 500
                terminal_detail = f"Native parsing failed for {file_name}: {profile.message}"

            if fallback_warning:
                if disable_fasttrack_fallback:
                    return VisualExceptionFallbackDecision(
                        terminal_status_code=503,
                        terminal_detail=(
                            "Required visual PDF chain failed and FastTrack/native fallback is disabled by "
                            "MODULE2_DISABLE_FASTTRACK_FALLBACK."
                        ),
                        try_docx_native_recovery=try_docx_native_recovery,
                        docx_native_recovery_reason="word_pdf_visual_error" if try_docx_native_recovery else "",
                    )
                return VisualExceptionFallbackDecision(
                    try_docx_native_recovery=try_docx_native_recovery,
                    docx_native_recovery_reason="word_pdf_visual_error" if try_docx_native_recovery else "",
                    fallback_warning=fallback_warning,
                    fallback_track="VisualTrack->FastTrackFallback",
                    fallback_context_label=f"{file_name}:FastTrackFallback",
                )

            return VisualExceptionFallbackDecision(
                terminal_status_code=terminal_status_code,
                terminal_detail=terminal_detail,
                try_docx_native_recovery=try_docx_native_recovery,
                docx_native_recovery_reason="word_pdf_visual_error" if try_docx_native_recovery else "",
            )

        if profile.unsupported_file_type:
            return VisualExceptionFallbackDecision(terminal_status_code=400, terminal_detail=profile.message)
        if profile.backend_unavailable:
            return VisualExceptionFallbackDecision(terminal_status_code=503, terminal_detail=profile.message)
        return VisualExceptionFallbackDecision(
            terminal_status_code=500,
            terminal_detail=f"Native parsing failed for {file_name}: {profile.message}",
        )


@dataclass(frozen=True)
class DocumentParseRecoveryOutcome:
    marked_markdown: str
    bbox_map: Dict[str, List[float]]
    table_blocks: List[Dict[str, Any]]
    figure_blocks: List[Dict[str, Any]]
    parse_stats: Dict[str, Any]
    parse_track: str
    parse_warning: str


class DocumentParseRecoveryRuntime:
    """Coordinate the primary parse attempt and the existing timeout/exception fallback policies."""

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
        parse_timeout_sec: float,
        parse_source_file_name: Optional[str],
        parse_source_file_bytes: Optional[bytes],
        progress_message: str,
        progress_extra: Dict[str, Any],
        resolve_parse_progress_ramp_sec: Callable[..., float],
        parse_attempt_runner,
        unpack_parse_output,
        visual_parse_policy_runtime,
        parse_fallback_coordinator_runtime,
        docx_native_recovery_runtime,
        fasttrack_fallback_runtime,
        word_suffix: str,
        original_file_is_word: bool,
        visual_chain_required: bool,
        docx_native_recovery_enabled: bool,
        visual_strict: bool,
        disable_fasttrack_fallback: bool,
        nonpdf_total_budget_sec: Optional[float],
        started_at_sec: float,
        nonpdf_guard_sec: float,
        current_parse_warning: Optional[str],
    ) -> DocumentParseRecoveryOutcome:
        parse_warning = str(current_parse_warning or "")
        active_parse_track = str(parse_track or "")

        try:
            parsed_output = await parse_attempt_runner(
                attempt_file_bytes=parse_input_bytes,
                attempt_file_name=parse_input_name,
                attempt_track=active_parse_track,
                attempt_timeout_sec=parse_timeout_sec,
                context_label=f"{file_name}:{active_parse_track}",
                attempt_source_file_name=parse_source_file_name,
                attempt_source_file_bytes=parse_source_file_bytes,
                heartbeat_stage="parsing",
                heartbeat_base_ratio=0.32,
                heartbeat_ceiling_ratio=0.74,
                heartbeat_ramp_sec=resolve_parse_progress_ramp_sec(
                    parse_input_bytes_len=len(parse_input_bytes),
                    timeout_sec=parse_timeout_sec,
                    parse_input_name=parse_input_name,
                    parse_track=active_parse_track,
                ),
                heartbeat_message=str(progress_message or ""),
                heartbeat_extra=dict(progress_extra or {}),
            )
            marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = unpack_parse_output(parsed_output)
            return DocumentParseRecoveryOutcome(
                marked_markdown=marked_markdown,
                bbox_map=bbox_map,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
                parse_stats=parse_stats,
                parse_track=active_parse_track,
                parse_warning=parse_warning,
            )
        except TimeoutError as exc:
            parse_timeout_decision = visual_parse_policy_runtime.resolve_timeout_fallback(
                file_name=file_name,
                parse_track=active_parse_track,
                parse_input_name=parse_input_name,
                original_file_is_word=original_file_is_word,
                word_suffix=word_suffix,
                parse_timeout_sec=parse_timeout_sec,
                visual_chain_required=visual_chain_required,
                nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                elapsed_sec=max(0.0, self._perf_counter() - started_at_sec),
                nonpdf_guard_sec=nonpdf_guard_sec,
            )
            if parse_timeout_decision.terminal_status_code is not None:
                raise HTTPException(
                    status_code=parse_timeout_decision.terminal_status_code,
                    detail=parse_timeout_decision.terminal_detail,
                ) from exc
            timeout_recovery_outcome = await parse_fallback_coordinator_runtime.try_docx_native_recovery(
                file_name=file_name,
                file_bytes=file_bytes,
                reason=parse_timeout_decision.docx_native_recovery_reason,
                enabled=parse_timeout_decision.try_docx_native_recovery and docx_native_recovery_enabled,
                current_warning=parse_warning,
                success_track="VisualTrack->NativeDocxRecoveryTimeout",
                success_warning="word_pdf_parse_timeout_recovered_native_docx",
                append_warning=visual_parse_policy_runtime.append_warning,
                docx_native_recovery_runtime=docx_native_recovery_runtime,
                parse_attempt_runner=parse_attempt_runner,
                unpack_parse_output=unpack_parse_output,
                timeout_hint_sec=parse_timeout_sec,
                nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                elapsed_sec=max(0.0, self._perf_counter() - started_at_sec),
                nonpdf_guard_sec=nonpdf_guard_sec,
            )
            parse_warning = timeout_recovery_outcome.parse_warning
            if timeout_recovery_outcome.resolved:
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = timeout_recovery_outcome.result
                active_parse_track = timeout_recovery_outcome.parse_track
                return DocumentParseRecoveryOutcome(
                    marked_markdown=marked_markdown,
                    bbox_map=bbox_map,
                    table_blocks=table_blocks,
                    figure_blocks=figure_blocks,
                    parse_stats=parse_stats,
                    parse_track=active_parse_track,
                    parse_warning=parse_warning,
                )
            if parse_timeout_decision.should_attempt_fasttrack_fallback:
                timeout_fallback_outcome = await parse_fallback_coordinator_runtime.run_fasttrack_fallback(
                    file_name=file_name,
                    parse_input_name=parse_input_name,
                    parse_input_bytes=parse_input_bytes,
                    fallback_timeout_sec=float(parse_timeout_decision.fallback_timeout_sec or parse_timeout_sec),
                    fallback_context_label=parse_timeout_decision.fallback_context_label,
                    current_warning=parse_warning,
                    success_track=parse_timeout_decision.fallback_track,
                    success_warning=parse_timeout_decision.fallback_hint,
                    append_warning=visual_parse_policy_runtime.append_warning,
                    fasttrack_fallback_runtime=fasttrack_fallback_runtime,
                    parse_attempt_runner=parse_attempt_runner,
                    unpack_parse_output=unpack_parse_output,
                    native_timeout_detail=parse_timeout_decision.native_timeout_detail,
                    parse_source_file_name=parse_source_file_name,
                    parse_source_file_bytes=parse_source_file_bytes,
                )
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = timeout_fallback_outcome.result
                active_parse_track = timeout_fallback_outcome.parse_track
                parse_warning = timeout_fallback_outcome.parse_warning
                return DocumentParseRecoveryOutcome(
                    marked_markdown=marked_markdown,
                    bbox_map=bbox_map,
                    table_blocks=table_blocks,
                    figure_blocks=figure_blocks,
                    parse_stats=parse_stats,
                    parse_track=active_parse_track,
                    parse_warning=parse_warning,
                )
            raise HTTPException(status_code=504, detail=parse_timeout_decision.native_timeout_detail) from exc
        except Exception as exc:
            parse_exception_decision = visual_parse_policy_runtime.resolve_exception_fallback(
                file_name=file_name,
                parse_track=active_parse_track,
                parse_input_name=parse_input_name,
                word_suffix=word_suffix,
                message=str(exc),
                visual_chain_required=visual_chain_required,
                visual_strict=visual_strict,
                disable_fasttrack_fallback=disable_fasttrack_fallback,
            )
            exception_recovery_outcome = await parse_fallback_coordinator_runtime.try_docx_native_recovery(
                file_name=file_name,
                file_bytes=file_bytes,
                reason=parse_exception_decision.docx_native_recovery_reason,
                enabled=parse_exception_decision.try_docx_native_recovery and docx_native_recovery_enabled,
                current_warning=parse_warning,
                success_track="VisualTrack->NativeDocxRecovery",
                success_warning="word_pdf_visual_recovered_native_docx",
                append_warning=visual_parse_policy_runtime.append_warning,
                docx_native_recovery_runtime=docx_native_recovery_runtime,
                parse_attempt_runner=parse_attempt_runner,
                unpack_parse_output=unpack_parse_output,
                timeout_hint_sec=parse_timeout_sec,
                nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                elapsed_sec=max(0.0, self._perf_counter() - started_at_sec),
                nonpdf_guard_sec=nonpdf_guard_sec,
            )
            parse_warning = exception_recovery_outcome.parse_warning
            if exception_recovery_outcome.resolved:
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = exception_recovery_outcome.result
                active_parse_track = exception_recovery_outcome.parse_track
                return DocumentParseRecoveryOutcome(
                    marked_markdown=marked_markdown,
                    bbox_map=bbox_map,
                    table_blocks=table_blocks,
                    figure_blocks=figure_blocks,
                    parse_stats=parse_stats,
                    parse_track=active_parse_track,
                    parse_warning=parse_warning,
                )
            if parse_exception_decision.should_attempt_fasttrack_fallback:
                exception_fallback_outcome = await parse_fallback_coordinator_runtime.run_fasttrack_fallback(
                    file_name=file_name,
                    parse_input_name=parse_input_name,
                    parse_input_bytes=parse_input_bytes,
                    fallback_timeout_sec=parse_timeout_sec,
                    fallback_context_label=parse_exception_decision.fallback_context_label,
                    current_warning=parse_warning,
                    success_track=parse_exception_decision.fallback_track,
                    success_warning=parse_exception_decision.fallback_warning,
                    append_warning=visual_parse_policy_runtime.append_warning,
                    fasttrack_fallback_runtime=fasttrack_fallback_runtime,
                    parse_attempt_runner=parse_attempt_runner,
                    unpack_parse_output=unpack_parse_output,
                    native_timeout_detail=f"Native parsing timed out for {file_name}",
                    parse_source_file_name=parse_source_file_name,
                    parse_source_file_bytes=parse_source_file_bytes,
                )
                marked_markdown, bbox_map, table_blocks, figure_blocks, parse_stats = exception_fallback_outcome.result
                active_parse_track = exception_fallback_outcome.parse_track
                parse_warning = exception_fallback_outcome.parse_warning
                return DocumentParseRecoveryOutcome(
                    marked_markdown=marked_markdown,
                    bbox_map=bbox_map,
                    table_blocks=table_blocks,
                    figure_blocks=figure_blocks,
                    parse_stats=parse_stats,
                    parse_track=active_parse_track,
                    parse_warning=parse_warning,
                )
            if parse_exception_decision.terminal_status_code is not None:
                raise HTTPException(
                    status_code=parse_exception_decision.terminal_status_code,
                    detail=parse_exception_decision.terminal_detail,
                ) from exc
            raise HTTPException(status_code=500, detail=f"Native parsing failed for {file_name}: {exc}") from exc
