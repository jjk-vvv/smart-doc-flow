from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
ParseResult = Tuple[str, Dict[str, List[float]], TableBlocks]
ParsePdfVisualFirst = Callable[..., Optional[ParseResult]]
VisualBackendAvailable = Callable[[], Tuple[bool, str]]
ParsePdfNative = Callable[..., Dict[str, Any]]
GetLastMineruRunMeta = Callable[[], Dict[str, Any]]
ParsePdfWithOcr = Callable[[bytes, int, Optional[List[int]]], ParseResult]


class PdfParseRuntime:
    """Coordinate the top-level PDF route while keeping parsing algorithms unchanged."""

    def __init__(
        self,
        *,
        enable_mineru_layout: bool,
        pipeline_mode: str,
        visual_first_allow_legacy_fallback: bool,
        parse_pdf_visual_first: ParsePdfVisualFirst,
        visual_backend_available: VisualBackendAvailable,
        parse_pdf_native: ParsePdfNative,
        get_last_mineru_run_meta: GetLastMineruRunMeta,
    ) -> None:
        self.enable_mineru_layout = bool(enable_mineru_layout)
        self.pipeline_mode = str(pipeline_mode or "").strip().lower()
        self.visual_first_allow_legacy_fallback = bool(visual_first_allow_legacy_fallback)
        self._parse_pdf_visual_first = parse_pdf_visual_first
        self._visual_backend_available = visual_backend_available
        self._parse_pdf_native = parse_pdf_native
        self._get_last_mineru_run_meta = get_last_mineru_run_meta

    def parse_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        track: str,
        reader: Any,
        total_pages: int,
        source_cache_identity: str = "",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
        last_figure_blocks: FigureBlocks,
        parse_pdf_with_ocr: ParsePdfWithOcr,
    ) -> Dict[str, Any]:
        effective_source_cache_identity = str(source_cache_identity or "").strip()
        source_cache_file_name = str(source_file_name or "").strip()
        if not effective_source_cache_identity:
            source_cache_bytes = None
            if isinstance(source_file_bytes, (bytes, bytearray)) and source_file_bytes:
                source_cache_bytes = bytes(source_file_bytes)
                if not source_cache_file_name:
                    source_cache_file_name = str(source_file_name or "").strip()
            elif isinstance(file_bytes, (bytes, bytearray)) and file_bytes:
                source_cache_bytes = bytes(file_bytes)
                if not source_cache_file_name:
                    source_cache_file_name = str(file_name or "").strip()
            if source_cache_bytes:
                effective_source_cache_identity = hashlib.sha256(source_cache_bytes).hexdigest()

        visual_fallback_stats: Dict[str, Any] = {}
        if (
            track == "VisualTrack"
            and self.enable_mineru_layout
            and self.pipeline_mode in {"visual_first", "hybrid"}
        ):
            visual_error: Exception | None = None
            try:
                visual_result = self._parse_pdf_visual_first(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    reader=reader,
                    page_count=total_pages,
                    source_cache_identity=effective_source_cache_identity,
                    source_file_name=source_file_name,
                    source_file_bytes=source_file_bytes,
                )
            except Exception as exc:
                visual_error = exc
                visual_result = None
            if visual_result is not None:
                stats_patch: Dict[str, Any] = {}
                if effective_source_cache_identity:
                    stats_patch = {
                        "source_cache_identity_applied": True,
                        "source_cache_identity_file_name": source_cache_file_name,
                    }
                return {
                    "kind": "visual_result",
                    "result": visual_result,
                    "stats_patch": stats_patch,
                }

            visual_fallback_stats = self._build_visual_fallback_stats(self._get_last_mineru_run_meta())
            if self.pipeline_mode == "visual_first" and not self.visual_first_allow_legacy_fallback:
                if visual_error is not None:
                    raise visual_error
                raise ValueError("Visual-first pipeline returned no usable result.")

        visual_backend_ready, _ = self._visual_backend_available()
        native_outcome = self._parse_pdf_native(
            reader=reader,
            file_bytes=file_bytes,
            track=track,
            total_pages=total_pages,
            visual_backend_ready=visual_backend_ready,
            last_figure_blocks=last_figure_blocks,
            parse_pdf_with_ocr=parse_pdf_with_ocr,
        )
        early_result = native_outcome.get("early_result")
        if early_result is not None:
            return {
                "kind": "native_early_result",
                "result": early_result,
            }

        stats_patch = {
            "source_cache_identity_applied": bool(effective_source_cache_identity),
            "source_cache_identity_file_name": source_cache_file_name,
        }
        if track == "VisualTrack" and visual_fallback_stats:
            stats_patch.update(visual_fallback_stats)
        return {
            "kind": "native_result",
            "result": (
                str(native_outcome.get("markdown") or ""),
                dict(native_outcome.get("bbox_map") or {}),
                list(native_outcome.get("table_blocks") or []),
            ),
            "stats": dict(native_outcome.get("stats") or {}),
            "stats_patch": stats_patch,
            "figure_blocks": list(native_outcome.get("figure_blocks") or []),
        }

    @staticmethod
    def _build_visual_fallback_stats(mineru_run_meta: Dict[str, Any]) -> Dict[str, Any]:
        stats: Dict[str, Any] = {}
        meta = dict(mineru_run_meta or {})
        if not meta:
            return stats
        visual_status = str(meta.get("status", "") or "").strip()
        if visual_status:
            stats["visual_first_fallback_reason"] = visual_status
        runtime_error = str(meta.get("runtime_error", "") or "").strip()
        fatal_runtime_error = str(meta.get("fatal_runtime_error", "") or "").strip()
        if runtime_error:
            stats["visual_first_runtime_error"] = runtime_error[:240]
        elif fatal_runtime_error:
            stats["visual_first_runtime_error"] = fatal_runtime_error[:240]
        return stats
