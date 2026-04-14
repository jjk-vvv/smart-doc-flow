from __future__ import annotations

import hashlib
import os
import time
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from fastapi import HTTPException


@dataclass(frozen=True)
class WordConversionPrecheckDecision:
    terminal_status_code: Optional[int] = None
    terminal_detail: str = ""

    @property
    def should_raise(self) -> bool:
        return self.terminal_status_code is not None


@dataclass(frozen=True)
class WordPdfFailureDecision:
    conversion_diag: Dict[str, Any] = field(default_factory=dict)
    terminal_status_code: Optional[int] = None
    terminal_detail: str = ""
    parse_track: str = ""
    parse_warning: str = ""
    use_original_input: bool = False
    emit_progress_message: str = ""

    @property
    def should_raise(self) -> bool:
        return self.terminal_status_code is not None


class WordConversionPolicyRuntime:
    """Build Word conversion diagnostics and fallback decisions without touching I/O."""

    @staticmethod
    def validate_preconditions(
        *,
        word_parse_via_pdf: bool,
        office_convert_enabled: bool,
        word_suffix: str,
    ) -> WordConversionPrecheckDecision:
        suffix = str(word_suffix or "").lower()
        if word_parse_via_pdf and not office_convert_enabled:
            return WordConversionPrecheckDecision(
                terminal_status_code=503,
                terminal_detail=(
                    "Word \u8f6c PDF \u529f\u80fd\u5df2\u7981\u7528\uff0c"
                    "\u5f53\u524d\u914d\u7f6e\u8981\u6c42 DOC/DOCX \u5fc5\u987b\u5148\u8f6c\u4e3a PDF \u540e\u518d\u89e3\u6790\u3002"
                ),
            )
        if (not word_parse_via_pdf) and suffix == ".doc" and not office_convert_enabled:
            return WordConversionPrecheckDecision(
                terminal_status_code=503,
                terminal_detail=(
                    "DOC \u539f\u751f\u89e3\u6790\u9700\u8981\u542f\u7528 Office \u8f6c\u6362\u80fd\u529b"
                    "\uff08\u7528\u4e8e DOC->DOCX \u9884\u5904\u7406\uff09\u3002"
                ),
            )
        return WordConversionPrecheckDecision()

    @staticmethod
    def build_word_pdf_success(
        *,
        file_name: str,
        convert_timeout_sec: float,
        total_elapsed_ms: int,
        preview_meta: Dict[str, Any],
        preview_job: Any,
    ) -> Dict[str, Any]:
        convert_meta = {
            "converter": str(preview_meta.get("converter", "") or getattr(preview_job, "converter", "") or "preview_job"),
            "elapsed_ms": int(preview_meta.get("elapsed_ms", 0) or getattr(preview_job, "elapsed_ms", 0) or 0),
        }
        artifact_path = str(preview_meta.get("artifact_path") or getattr(preview_job, "artifact_path", "") or "").strip()
        artifact_url = str(preview_meta.get("artifact_url") or getattr(preview_job, "artifact_url", "") or "").strip()
        conversion_diag = {
            "office_pdf_converted": True,
            "office_pdf_converter": str(convert_meta.get("converter", "")),
            "office_pdf_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
            "office_pdf_timeout_sec": round(float(convert_timeout_sec), 3),
            "office_pdf_preview_path": artifact_path,
            "office_pdf_preview_url": artifact_url,
            "office_pdf_preview_reused": True,
            "office_pdf_preview_job_id": str(
                preview_meta.get("office_pdf_preview_job_id", "") or getattr(preview_job, "job_id", "") or ""
            ),
            "office_pdf_preview_waited_ms": int(preview_meta.get("waited_ms", 0) or 0),
            "office_pdf_total_ms": int(total_elapsed_ms),
        }
        preview_error = str(preview_meta.get("office_pdf_preview_error", "") or "").strip()
        if preview_error:
            conversion_diag["office_pdf_preview_error"] = preview_error
        return {
            "parse_input_name": f"{Path(file_name).stem}.pdf",
            "parse_track": "VisualTrack",
            "conversion_diag": conversion_diag,
        }

    @staticmethod
    def resolve_word_pdf_failure(
        *,
        file_name: str,
        word_suffix: str,
        exc: Exception,
        convert_timeout_sec: float,
        total_elapsed_ms: int,
        word_parse_via_pdf: bool,
        docx_native_recovery_enabled: bool,
        allow_native_fallback: bool,
    ) -> WordPdfFailureDecision:
        suffix = str(word_suffix or "").lower()
        error_text = f"{type(exc).__name__}: {exc}"
        conversion_diag: Dict[str, Any] = {
            "office_pdf_converted": False,
            "office_pdf_error": error_text,
            "office_pdf_timeout_sec": round(float(convert_timeout_sec), 3),
            "office_pdf_total_ms": int(total_elapsed_ms),
        }
        docx_native_recovery_requested = suffix == ".docx" and bool(docx_native_recovery_enabled)
        if docx_native_recovery_requested:
            conversion_diag["docx_native_recovery_requested"] = True
            conversion_diag["docx_native_recovery_reason"] = error_text

        if (not docx_native_recovery_requested) and ((word_parse_via_pdf and not allow_native_fallback) or suffix == ".doc"):
            return WordPdfFailureDecision(
                conversion_diag=conversion_diag,
                terminal_status_code=422,
                terminal_detail=f"Word \u8f6c PDF \u5931\u8d25\uff0c\u65e0\u6cd5\u5904\u7406 {file_name}: {error_text}",
            )

        if docx_native_recovery_requested:
            return WordPdfFailureDecision(
                conversion_diag=conversion_diag,
                parse_track="NativeDocx",
                parse_warning="docx_native_recovery_after_pdf_failure",
                use_original_input=True,
                emit_progress_message="Word PDF \u94fe\u8def\u5931\u8d25\uff0c\u5df2\u5207\u6362 DOCX \u539f\u751f\u6062\u590d\u89e3\u6790",
            )

        return WordPdfFailureDecision(
            conversion_diag=conversion_diag,
            parse_track="FastTrack",
            parse_warning=f"doc_to_pdf_fallback_native:{type(exc).__name__}",
            use_original_input=True,
        )

    @staticmethod
    def build_doc_to_docx_success(
        *,
        file_name: str,
        convert_timeout_sec: float,
        total_elapsed_ms: int,
        convert_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "parse_input_name": f"{Path(file_name).stem}.docx",
            "conversion_diag": {
                "doc_to_docx_converted": True,
                "doc_to_docx_converter": str(convert_meta.get("converter", "")),
                "doc_to_docx_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
                "doc_to_docx_timeout_sec": round(float(convert_timeout_sec), 3),
                "doc_to_docx_total_ms": int(total_elapsed_ms),
            },
        }

    @staticmethod
    def build_doc_to_docx_failure(
        *,
        file_name: str,
        exc: Exception,
        convert_timeout_sec: float,
        total_elapsed_ms: int,
    ) -> Dict[str, Any]:
        error_text = f"{type(exc).__name__}: {exc}"
        return {
            "conversion_diag": {
                "doc_to_docx_converted": False,
                "doc_to_docx_error": error_text,
                "doc_to_docx_timeout_sec": round(float(convert_timeout_sec), 3),
                "doc_to_docx_total_ms": int(total_elapsed_ms),
            },
            "terminal_status_code": 422,
            "terminal_detail": f"DOC \u8f6c DOCX \u5931\u8d25\uff0c\u65e0\u6cd5\u5904\u7406 {file_name}: {error_text}",
        }


@dataclass(frozen=True)
class WordConversionExecutionOutcome:
    parse_input_name: str
    parse_input_bytes: bytes
    parse_track: str
    parse_warning: str
    conversion_diag: Dict[str, Any]


class WordConversionExecutionRuntime:
    """Execute Word-family conversion branches without changing policy decisions."""

    def __init__(self, *, getenv=os.getenv, perf_counter: Callable[[], float] = time.perf_counter) -> None:
        self._getenv = getenv
        self._perf_counter = perf_counter

    async def prepare_word_via_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: Optional[float],
        word_convert_budget_sec: Optional[float],
        nonpdf_guard_sec: float,
        started_at_sec: float,
        word_suffix: str,
        word_parse_via_pdf: bool,
        docx_native_recovery_enabled: bool,
        resolve_conversion_timeout,
        build_word_pdf_success,
        resolve_word_pdf_failure,
        emit_progress: Callable[..., Awaitable[None]],
        word_pdf_semaphore: AbstractAsyncContextManager[Any],
        ensure_preview_job_started,
        await_or_reuse_pdf,
        run_with_progress_heartbeat,
    ) -> WordConversionExecutionOutcome:
        convert_timeout_default = max(20.0, float(self._getenv("MODULE2_DOC_TO_PDF_TIMEOUT_SEC", "60")))
        convert_timeout_decision = resolve_conversion_timeout(
            file_name=file_name,
            conversion_label="Word->PDF",
            convert_timeout_default=convert_timeout_default,
            word_convert_budget_sec=word_convert_budget_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            elapsed_before_convert_sec=max(0.0, self._perf_counter() - started_at_sec),
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
        )
        if not convert_timeout_decision.timeout_sec:
            raise HTTPException(status_code=504, detail=convert_timeout_decision.exhausted_detail)

        convert_timeout_sec = float(convert_timeout_decision.timeout_sec)
        convert_t0 = self._perf_counter()
        try:
            await emit_progress(
                "converting",
                0.14,
                "\u6b63\u5728\u5c06 Word \u6587\u6863\u8f6c\u6362\u4e3a PDF\u3002",
            )
            async with word_pdf_semaphore:
                preview_job = await ensure_preview_job_started(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    file_hash=file_hash,
                )
                try:
                    pdf_bytes, preview_meta = await run_with_progress_heartbeat(
                        await_or_reuse_pdf(
                            file_name=file_name,
                            file_hash=file_hash,
                            timeout_sec=convert_timeout_sec,
                        ),
                        emit_progress=emit_progress,
                        stage="converting",
                        base_ratio=0.14,
                        ceiling_ratio=0.23,
                        ramp_sec=min(max(6.0, convert_timeout_sec * 0.7), 18.0),
                        message="\u6b63\u5728\u7b49\u5f85 Office \u9884\u89c8\u8f6c\u6362\u7ed3\u679c\u3002",
                    )
                except TimeoutError as exc:
                    raise HTTPException(
                        status_code=504,
                        detail=(
                            f"Word \u9884\u89c8\u8f6c PDF \u8d85\u65f6\uff0c\u65e0\u6cd5\u7ee7\u7eed\u89e3\u6790: "
                            f"{file_name}: {exc}"
                        ),
                    ) from exc

            if pdf_bytes is None:
                preview_error = str(preview_meta.get("office_pdf_preview_error", "") or "").strip() or str(
                    getattr(preview_job, "error", "") or "office_preview_failed"
                )
                raise RuntimeError(preview_error)

            word_pdf_success = build_word_pdf_success(
                file_name=file_name,
                convert_timeout_sec=convert_timeout_sec,
                total_elapsed_ms=int((self._perf_counter() - convert_t0) * 1000),
                preview_meta=preview_meta,
                preview_job=preview_job,
            )
            await emit_progress(
                "converting",
                0.24,
                "\u6587\u6863\u5df2\u8f6c\u6362\u4e3a PDF\uff0c\u6b63\u5728\u51c6\u5907\u7248\u9762\u89e3\u6790\u3002",
            )
            return WordConversionExecutionOutcome(
                parse_input_name=str(word_pdf_success["parse_input_name"] or file_name),
                parse_input_bytes=pdf_bytes,
                parse_track=str(word_pdf_success["parse_track"] or "VisualTrack"),
                parse_warning="",
                conversion_diag=dict(word_pdf_success["conversion_diag"] or {}),
            )
        except Exception as exc:
            word_pdf_failure = resolve_word_pdf_failure(
                file_name=file_name,
                word_suffix=word_suffix,
                exc=exc,
                convert_timeout_sec=convert_timeout_sec,
                total_elapsed_ms=int((self._perf_counter() - convert_t0) * 1000),
                word_parse_via_pdf=word_parse_via_pdf,
                docx_native_recovery_enabled=docx_native_recovery_enabled,
                allow_native_fallback=(
                    word_suffix == ".docx"
                    and (self._getenv("MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK", "false").lower() in {"1", "true", "yes"})
                ),
            )
            if word_pdf_failure.emit_progress_message:
                await emit_progress("converting", 0.24, word_pdf_failure.emit_progress_message)
            if word_pdf_failure.should_raise:
                raise HTTPException(
                    status_code=int(word_pdf_failure.terminal_status_code or 422),
                    detail=word_pdf_failure.terminal_detail,
                ) from exc
            return WordConversionExecutionOutcome(
                parse_input_name=file_name,
                parse_input_bytes=file_bytes,
                parse_track=str(word_pdf_failure.parse_track or "FastTrack"),
                parse_warning=str(word_pdf_failure.parse_warning or ""),
                conversion_diag=dict(word_pdf_failure.conversion_diag or {}),
            )

    async def prepare_doc_to_docx_fasttrack(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: Optional[float],
        word_convert_budget_sec: Optional[float],
        nonpdf_guard_sec: float,
        started_at_sec: float,
        resolve_conversion_timeout,
        build_doc_to_docx_success,
        build_doc_to_docx_failure,
        convert_doc_to_docx_with_timeout,
    ) -> WordConversionExecutionOutcome:
        convert_timeout_default = max(12.0, float(self._getenv("MODULE2_DOC_TO_DOCX_TIMEOUT_SEC", "45")))
        convert_timeout_decision = resolve_conversion_timeout(
            file_name=file_name,
            conversion_label="DOC->DOCX",
            convert_timeout_default=convert_timeout_default,
            word_convert_budget_sec=word_convert_budget_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            elapsed_before_convert_sec=max(0.0, self._perf_counter() - started_at_sec),
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_guard_sec=nonpdf_guard_sec,
        )
        if not convert_timeout_decision.timeout_sec:
            raise HTTPException(status_code=504, detail=convert_timeout_decision.exhausted_detail)

        convert_timeout_sec = float(convert_timeout_decision.timeout_sec)
        convert_t0 = self._perf_counter()
        try:
            docx_bytes, convert_meta = await convert_doc_to_docx_with_timeout(
                file_name=file_name,
                file_bytes=file_bytes,
                timeout_sec=convert_timeout_sec,
            )
            doc_to_docx_success = build_doc_to_docx_success(
                file_name=file_name,
                convert_timeout_sec=convert_timeout_sec,
                total_elapsed_ms=int((self._perf_counter() - convert_t0) * 1000),
                convert_meta=convert_meta,
            )
            return WordConversionExecutionOutcome(
                parse_input_name=str(doc_to_docx_success["parse_input_name"] or f"{Path(file_name).stem}.docx"),
                parse_input_bytes=docx_bytes,
                parse_track="FastTrack",
                parse_warning="",
                conversion_diag=dict(doc_to_docx_success["conversion_diag"] or {}),
            )
        except Exception as exc:
            doc_to_docx_failure = build_doc_to_docx_failure(
                file_name=file_name,
                exc=exc,
                convert_timeout_sec=convert_timeout_sec,
                total_elapsed_ms=int((self._perf_counter() - convert_t0) * 1000),
            )
            raise HTTPException(
                status_code=int(doc_to_docx_failure["terminal_status_code"] or 422),
                detail=str(doc_to_docx_failure["terminal_detail"] or ""),
            ) from exc


ApplyDocxChartMerge = Callable[[], None]


class WordPdfContextRuntime:
    """Resolve PDF-from-DOCX source context and related stats patches."""

    @staticmethod
    def build_parse_context(
        *,
        file_name: str,
        source_file_name: Optional[str],
        source_file_bytes: Any,
        use_source_signals: bool,
    ) -> Dict[str, Any]:
        source_suffix = Path(source_file_name or "").suffix.lower()
        normalized_source_bytes = bytes(source_file_bytes) if isinstance(source_file_bytes, (bytes, bytearray)) else b""
        is_word_pdf_context = (
            str(file_name or "").lower().endswith(".pdf")
            and source_suffix == ".docx"
            and bool(normalized_source_bytes)
        )
        return {
            "is_word_pdf_context": is_word_pdf_context,
            "parse_source_file_name": source_file_name if (is_word_pdf_context and use_source_signals) else None,
            "parse_source_file_bytes": source_file_bytes if (is_word_pdf_context and use_source_signals) else None,
            "parse_source_cache_identity": hashlib.sha256(normalized_source_bytes).hexdigest() if is_word_pdf_context else "",
        }

    @staticmethod
    def build_source_stats_patch(
        *,
        source_file_name: Optional[str],
        parse_source_file_name: Optional[str],
        parse_source_cache_identity: str,
        use_source_signals: bool,
        chart_xml_merge_enabled: bool,
    ) -> Dict[str, Any]:
        stats_patch: Dict[str, Any] = {
            "word_pdf_parse_use_source_signals": bool(use_source_signals),
            "word_pdf_parse_source_signals_applied": bool(parse_source_file_name),
            "word_pdf_parse_source_cache_identity_seeded": bool(parse_source_cache_identity),
            "word_pdf_docx_chart_xml_merge_enabled": bool(chart_xml_merge_enabled),
        }
        if parse_source_cache_identity:
            stats_patch["source_cache_identity_applied"] = True
            stats_patch["source_cache_identity_file_name"] = str(source_file_name or "")
        return stats_patch

    @staticmethod
    def build_docx_chart_merge_stats_patch(
        *,
        enabled: bool,
        source_file_name: Optional[str],
        apply_docx_chart_merge: ApplyDocxChartMerge,
    ) -> Dict[str, Any]:
        if not enabled:
            return {
                "docx_source_chart_merge_applied": False,
                "docx_source_chart_merge_skipped": True,
                "docx_source_chart_merge_ms": 0,
                "docx_source_file_name": str(source_file_name or ""),
            }

        merge_t0 = time.perf_counter()
        stats_patch: Dict[str, Any] = {}
        try:
            apply_docx_chart_merge()
            stats_patch["docx_source_chart_merge_applied"] = True
        except Exception as exc:
            stats_patch["docx_source_chart_merge_applied"] = False
            stats_patch["docx_source_chart_merge_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            stats_patch["docx_source_chart_merge_ms"] = int((time.perf_counter() - merge_t0) * 1000)
            stats_patch["docx_source_file_name"] = str(source_file_name or "")
        return stats_patch


@dataclass(frozen=True)
class WordInputPreparationOutcome:
    parse_input_name: str
    parse_input_bytes: bytes
    parse_track: str
    parse_warning: str
    conversion_diag: Dict[str, Any]
    word_suffix: str


class WordInputPreparationRuntime:
    """Prepare Word-family inputs for the parse pipeline without changing conversion semantics."""

    def __init__(
        self,
        *,
        getenv=os.getenv,
        perf_counter: Callable[[], float] = time.perf_counter,
        word_conversion_execution_runtime: WordConversionExecutionRuntime | None = None,
    ) -> None:
        self._getenv = getenv
        self._perf_counter = perf_counter
        self._word_conversion_execution_runtime = word_conversion_execution_runtime or WordConversionExecutionRuntime(
            getenv=getenv,
            perf_counter=perf_counter,
        )

    async def prepare(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        parse_track: str,
        parse_warning: Optional[str],
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: Optional[float],
        word_convert_budget_sec: Optional[float],
        nonpdf_guard_sec: float,
        started_at_sec: float,
        input_is_word: bool,
        word_parse_via_pdf: bool,
        office_convert_enabled: bool,
        docx_native_recovery_enabled: bool,
        validate_preconditions,
        resolve_conversion_timeout,
        build_word_pdf_success,
        resolve_word_pdf_failure,
        build_doc_to_docx_success,
        build_doc_to_docx_failure,
        emit_progress: Callable[..., Awaitable[None]],
        word_pdf_semaphore: AbstractAsyncContextManager[Any],
        ensure_preview_job_started,
        await_or_reuse_pdf,
        run_with_progress_heartbeat,
        convert_doc_to_docx_with_timeout,
    ) -> WordInputPreparationOutcome:
        resolved_parse_input_name = file_name
        resolved_parse_input_bytes = file_bytes
        resolved_parse_track = str(parse_track or "")
        resolved_parse_warning = str(parse_warning or "")
        conversion_diag: Dict[str, Any] = {}
        word_suffix = Path(file_name).suffix.lower()

        if input_is_word:
            word_precheck = validate_preconditions(
                word_parse_via_pdf=word_parse_via_pdf,
                office_convert_enabled=office_convert_enabled,
                word_suffix=word_suffix,
            )
            if word_precheck.should_raise:
                raise HTTPException(
                    status_code=int(word_precheck.terminal_status_code or 503),
                    detail=word_precheck.terminal_detail,
                )

        if input_is_word and word_parse_via_pdf and office_convert_enabled:
            word_pdf_outcome = await self._word_conversion_execution_runtime.prepare_word_via_pdf(
                file_name=file_name,
                file_bytes=file_bytes,
                file_hash=file_hash,
                parse_timeout_sec=parse_timeout_sec,
                extract_timeout_sec=extract_timeout_sec,
                nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                word_convert_budget_sec=word_convert_budget_sec,
                nonpdf_guard_sec=nonpdf_guard_sec,
                started_at_sec=started_at_sec,
                word_suffix=word_suffix,
                word_parse_via_pdf=word_parse_via_pdf,
                docx_native_recovery_enabled=docx_native_recovery_enabled,
                resolve_conversion_timeout=resolve_conversion_timeout,
                build_word_pdf_success=build_word_pdf_success,
                resolve_word_pdf_failure=resolve_word_pdf_failure,
                emit_progress=emit_progress,
                word_pdf_semaphore=word_pdf_semaphore,
                ensure_preview_job_started=ensure_preview_job_started,
                await_or_reuse_pdf=await_or_reuse_pdf,
                run_with_progress_heartbeat=run_with_progress_heartbeat,
            )
            resolved_parse_input_name = word_pdf_outcome.parse_input_name
            resolved_parse_input_bytes = word_pdf_outcome.parse_input_bytes
            resolved_parse_track = word_pdf_outcome.parse_track
            resolved_parse_warning = word_pdf_outcome.parse_warning
            conversion_diag = word_pdf_outcome.conversion_diag
        elif input_is_word and (not word_parse_via_pdf):
            resolved_parse_track = "FastTrack"
            if word_suffix == ".doc":
                doc_to_docx_outcome = await self._word_conversion_execution_runtime.prepare_doc_to_docx_fasttrack(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    parse_timeout_sec=parse_timeout_sec,
                    extract_timeout_sec=extract_timeout_sec,
                    nonpdf_total_budget_sec=nonpdf_total_budget_sec,
                    word_convert_budget_sec=word_convert_budget_sec,
                    nonpdf_guard_sec=nonpdf_guard_sec,
                    started_at_sec=started_at_sec,
                    resolve_conversion_timeout=resolve_conversion_timeout,
                    build_doc_to_docx_success=build_doc_to_docx_success,
                    build_doc_to_docx_failure=build_doc_to_docx_failure,
                    convert_doc_to_docx_with_timeout=convert_doc_to_docx_with_timeout,
                )
                resolved_parse_input_name = doc_to_docx_outcome.parse_input_name
                resolved_parse_input_bytes = doc_to_docx_outcome.parse_input_bytes
                resolved_parse_track = doc_to_docx_outcome.parse_track
                resolved_parse_warning = doc_to_docx_outcome.parse_warning
                conversion_diag = doc_to_docx_outcome.conversion_diag

        if resolved_parse_input_name.lower().endswith(".pdf"):
            resolved_parse_track = "VisualTrack"

        return WordInputPreparationOutcome(
            parse_input_name=resolved_parse_input_name,
            parse_input_bytes=resolved_parse_input_bytes,
            parse_track=resolved_parse_track,
            parse_warning=resolved_parse_warning,
            conversion_diag=conversion_diag,
            word_suffix=word_suffix,
        )
