from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


NormalizeText = Callable[[str], str]
SummarizePdfMetadataSignals = Callable[[Any], Dict[str, Any]]
ClassifyPdfVisualProfile = Callable[..., Dict[str, Any]]
ResolveVisualRuntimeLimits = Callable[..., Dict[str, Any]]
PageLines = Dict[int, List[str]]
PageChunks = Dict[int, List[str]]
PageDimensions = Dict[int, Tuple[float, float]]
SplitPageText = Callable[[str], List[str]]
AppendRef = Callable[[List[str], Dict[str, List[float]], str, str, List[float]], None]


class VisualRuntimeLimitsRuntime:
    """Resolve visual-first runtime limits from document and source signals."""

    def __init__(
        self,
        *,
        image_extensions: Set[str],
        visual_max_objects: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_chart_score_min: int,
        visual_figure_cueless_fallback_max: int,
        visual_figure_refine_budget: int,
        visual_figure_refine_min_score: int,
        visual_runtime_large_doc_page_threshold: int,
        visual_runtime_large_doc_image_threshold: int,
        visual_runtime_large_doc_max_objects: int,
        visual_runtime_large_doc_figure_max_per_page: int,
        visual_runtime_large_doc_cueless_fallback_max: int,
        visual_runtime_large_doc_chart_score_min: int,
        visual_runtime_large_doc_refine_budget: int,
        visual_runtime_extreme_doc_page_threshold: int,
        visual_runtime_extreme_doc_max_objects: int,
        visual_runtime_extreme_doc_figure_max_per_page: int,
        visual_runtime_extreme_doc_cueless_fallback_max: int,
        visual_runtime_extreme_doc_chart_score_min: int,
        visual_runtime_extreme_doc_refine_budget: int,
    ) -> None:
        self.image_extensions = {str(item).lower() for item in image_extensions}
        self.visual_max_objects = int(visual_max_objects or 0)
        self.visual_table_max_per_page = int(visual_table_max_per_page or 0)
        self.visual_figure_max_per_page = int(visual_figure_max_per_page or 0)
        self.visual_figure_chart_score_min = int(visual_figure_chart_score_min or 0)
        self.visual_figure_cueless_fallback_max = int(visual_figure_cueless_fallback_max or 0)
        self.visual_figure_refine_budget = int(visual_figure_refine_budget or 0)
        self.visual_figure_refine_min_score = int(visual_figure_refine_min_score or 0)
        self.visual_runtime_large_doc_page_threshold = int(visual_runtime_large_doc_page_threshold or 0)
        self.visual_runtime_large_doc_image_threshold = int(visual_runtime_large_doc_image_threshold or 0)
        self.visual_runtime_large_doc_max_objects = int(visual_runtime_large_doc_max_objects or 0)
        self.visual_runtime_large_doc_figure_max_per_page = int(visual_runtime_large_doc_figure_max_per_page or 0)
        self.visual_runtime_large_doc_cueless_fallback_max = int(visual_runtime_large_doc_cueless_fallback_max or 0)
        self.visual_runtime_large_doc_chart_score_min = int(visual_runtime_large_doc_chart_score_min or 0)
        self.visual_runtime_large_doc_refine_budget = int(visual_runtime_large_doc_refine_budget or 0)
        self.visual_runtime_extreme_doc_page_threshold = int(visual_runtime_extreme_doc_page_threshold or 0)
        self.visual_runtime_extreme_doc_max_objects = int(visual_runtime_extreme_doc_max_objects or 0)
        self.visual_runtime_extreme_doc_figure_max_per_page = int(visual_runtime_extreme_doc_figure_max_per_page or 0)
        self.visual_runtime_extreme_doc_cueless_fallback_max = int(visual_runtime_extreme_doc_cueless_fallback_max or 0)
        self.visual_runtime_extreme_doc_chart_score_min = int(visual_runtime_extreme_doc_chart_score_min or 0)
        self.visual_runtime_extreme_doc_refine_budget = int(visual_runtime_extreme_doc_refine_budget or 0)

    def summarize_visual_source_signals(
        self,
        *,
        source_file_name: Optional[str],
        source_file_bytes: Optional[bytes],
    ) -> Dict[str, Any]:
        source_suffix = Path(source_file_name or "").suffix.lower()
        summary: Dict[str, Any] = {
            "source_suffix": source_suffix,
            "source_docx_media_count": 0,
            "source_docx_chart_xml_count": 0,
        }
        if source_suffix != ".docx" or not isinstance(source_file_bytes, (bytes, bytearray)) or not source_file_bytes:
            return summary
        try:
            with zipfile.ZipFile(io.BytesIO(bytes(source_file_bytes))) as zf:
                media_count = 0
                chart_count = 0
                for name in zf.namelist():
                    normalized = str(name or "").replace("\\", "/")
                    if normalized.startswith("word/media/") and Path(normalized).suffix.lower() in self.image_extensions:
                        media_count += 1
                    elif normalized.startswith("word/charts/") and normalized.lower().endswith(".xml"):
                        chart_count += 1
        except Exception as exc:
            summary["source_archive_error"] = type(exc).__name__
            return summary
        summary["source_docx_media_count"] = media_count
        summary["source_docx_chart_xml_count"] = chart_count
        return summary

    def resolve_visual_runtime_limits(
        self,
        *,
        file_name: str,
        source_file_name: Optional[str],
        source_file_bytes: Optional[bytes],
        page_count: int,
        layout_page_count: Optional[int],
        objects: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        image_object_count = 0
        table_object_count = 0
        for item in objects:
            obj_type = str(item.get("object_type", "") or "")
            if obj_type == "image":
                image_object_count += 1
            elif obj_type == "table":
                table_object_count += 1

        source_signals = self.summarize_visual_source_signals(
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
        )
        source_suffix = str(source_signals.get("source_suffix", "") or "")
        source_docx_media_count = int(source_signals.get("source_docx_media_count", 0) or 0)
        source_docx_chart_xml_count = int(source_signals.get("source_docx_chart_xml_count", 0) or 0)
        is_docx_source = source_suffix == ".docx"
        effective_layout_page_count = max(1, min(int(layout_page_count or page_count or 1), int(page_count or 1)))
        large_visual_doc = (
            page_count >= self.visual_runtime_large_doc_page_threshold
            and image_object_count >= self.visual_runtime_large_doc_image_threshold
        )
        extreme_visual_doc = page_count >= self.visual_runtime_extreme_doc_page_threshold
        docx_chart_heavy = is_docx_source and (
            image_object_count >= max(6, self.visual_runtime_large_doc_image_threshold - 2)
            or source_docx_media_count >= 8
            or source_docx_chart_xml_count >= 1
        )

        profile = "default"
        max_objects = self.visual_max_objects
        table_max_per_page = self.visual_table_max_per_page
        figure_max_per_page = self.visual_figure_max_per_page
        chart_score_min = self.visual_figure_chart_score_min
        cueless_fallback_max = self.visual_figure_cueless_fallback_max
        figure_refine_budget = self.visual_figure_refine_budget
        if extreme_visual_doc:
            profile = "extreme_visual_doc"
            max_objects = min(max_objects, self.visual_runtime_extreme_doc_max_objects)
            figure_max_per_page = min(figure_max_per_page, self.visual_runtime_extreme_doc_figure_max_per_page)
            cueless_fallback_max = min(cueless_fallback_max, self.visual_runtime_extreme_doc_cueless_fallback_max)
            chart_score_min = max(chart_score_min, self.visual_runtime_extreme_doc_chart_score_min)
            figure_refine_budget = min(figure_refine_budget, self.visual_runtime_extreme_doc_refine_budget)
        elif docx_chart_heavy or large_visual_doc:
            profile = "docx_chart_heavy" if docx_chart_heavy else "large_visual_doc"
            max_objects = min(max_objects, self.visual_runtime_large_doc_max_objects)
            figure_max_per_page = min(figure_max_per_page, self.visual_runtime_large_doc_figure_max_per_page)
            cueless_fallback_max = min(cueless_fallback_max, self.visual_runtime_large_doc_cueless_fallback_max)
            chart_score_min = max(chart_score_min, self.visual_runtime_large_doc_chart_score_min)
            figure_refine_budget = min(figure_refine_budget, self.visual_runtime_large_doc_refine_budget)

        return {
            "profile": profile,
            "max_objects": max_objects,
            "table_max_per_page": table_max_per_page,
            "figure_max_per_page": figure_max_per_page,
            "chart_score_min": chart_score_min,
            "cueless_fallback_max": cueless_fallback_max,
            "figure_refine_budget": figure_refine_budget,
            "figure_refine_min_score": self.visual_figure_refine_min_score,
            "page_count": int(page_count),
            "layout_page_count": int(effective_layout_page_count),
            "image_object_count": int(image_object_count),
            "table_object_count": int(table_object_count),
            "source_signals": source_signals,
            "source_doc_name": str(source_file_name or ""),
            "doc_name": str(file_name or ""),
        }


class VisualPdfPrepareRuntime:
    """Prepare native PDF page context and bootstrap placeholder refs."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        split_page_text: SplitPageText,
        append_ref: AppendRef,
    ) -> None:
        self._normalize_text = normalize_text
        self._split_page_text = split_page_text
        self._append_ref = append_ref

    def prepare_context(
        self,
        *,
        reader: Any,
        page_count: int,
        mineru_page_lines: PageLines,
    ) -> Dict[str, Any]:
        native_page_count = max(0, int(page_count or 0))
        native_page_lines: PageLines = {}
        native_page_chunks: PageChunks = {}

        native_context_t0 = time.perf_counter()
        for page_idx in range(native_page_count):
            page_no = page_idx + 1
            raw_text = self._extract_page_text(reader=reader, page_idx=page_idx)
            text = self._normalize_text(raw_text)
            chunks = self._split_page_text(text)
            if chunks:
                native_page_chunks[page_no] = list(chunks)

            lines = [self._normalize_text(line) for line in raw_text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                native_page_lines[page_no] = lines[:120]
        native_context_ms = int((time.perf_counter() - native_context_t0) * 1000)

        merge_context_t0 = time.perf_counter()
        page_lines = self.merge_page_line_context(native_page_lines, mineru_page_lines)
        merge_context_ms = int((time.perf_counter() - merge_context_t0) * 1000)

        return {
            "native_page_lines": native_page_lines,
            "native_page_chunks": native_page_chunks,
            "page_lines": page_lines,
            "native_context_ms": int(native_context_ms),
            "merge_context_ms": int(merge_context_ms),
        }

    def build_initial_refs(
        self,
        *,
        reader: Any,
        page_count: int,
        native_page_chunks: PageChunks,
    ) -> Dict[str, Any]:
        native_page_count = max(0, int(page_count or 0))
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_dims = self.build_page_dimensions(reader=reader, page_count=native_page_count)

        for page_no in range(1, native_page_count + 1):
            chunks = native_page_chunks.get(page_no, [])
            if chunks:
                for chunk_idx, chunk in enumerate(chunks, start=1):
                    ref_id = f"p{page_no}_c{chunk_idx}"
                    self._append_ref(parts, bbox_map, ref_id, chunk, [float(page_no), 0.0, 0.0, 1.0, 1.0])
                continue

            ref_id = f"p{page_no}_c1"
            placeholder = f"[Page {page_no}] No extractable native text."
            self._append_ref(parts, bbox_map, ref_id, placeholder, [float(page_no), 0.0, 0.0, 1.0, 1.0])

        return {
            "parts": parts,
            "bbox_map": bbox_map,
            "page_dims": page_dims,
        }

    @staticmethod
    def merge_page_line_context(
        native_lines: PageLines,
        mineru_lines: PageLines,
    ) -> PageLines:
        merged: PageLines = {}
        pages = set(native_lines.keys()) | set(mineru_lines.keys())
        for page_no in pages:
            out: List[str] = []
            seen = set()
            for source in (native_lines.get(page_no, []), mineru_lines.get(page_no, [])):
                for line in source:
                    text = " ".join(str(line or "").split())
                    if not text:
                        continue
                    key = text[:220].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(text)
                    if len(out) >= 160:
                        break
                if len(out) >= 160:
                    break
            if out:
                merged[page_no] = out
        return merged

    @staticmethod
    def build_page_dimensions(reader: Any, page_count: int) -> PageDimensions:
        out: PageDimensions = {}
        for idx in range(max(0, int(page_count or 0))):
            page_no = idx + 1
            try:
                page = reader.pages[idx]
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
            except Exception:
                width = 1.0
                height = 1.0
            out[page_no] = (max(width, 1.0), max(height, 1.0))
        return out

    @staticmethod
    def _extract_page_text(*, reader: Any, page_idx: int) -> str:
        try:
            return reader.pages[page_idx].extract_text() or ""
        except Exception:
            return ""


class VisualPdfBootstrapRuntime:
    """Bootstrap visual-first PDF probing, MinerU method selection, and layout extraction."""

    def __init__(
        self,
        *,
        visual_probe_pages: int,
        visual_first_max_pages: int,
        max_pages: int,
        mineru_method: str,
        visual_runtime_extreme_doc_page_threshold: int,
        visual_runtime_office_text_layout_page_cap: int,
        visual_runtime_mixed_text_layout_page_cap: int,
        visual_runtime_extreme_doc_layout_page_cap: int,
        normalize_text: NormalizeText,
        summarize_pdf_metadata_signals: SummarizePdfMetadataSignals,
        classify_pdf_visual_profile: ClassifyPdfVisualProfile,
        resolve_visual_runtime_limits: ResolveVisualRuntimeLimits,
    ) -> None:
        self.visual_probe_pages = int(visual_probe_pages or 0)
        self.visual_first_max_pages = int(visual_first_max_pages or 0)
        self.max_pages = int(max_pages or 0)
        self.mineru_method = str(mineru_method or "")
        self.visual_runtime_extreme_doc_page_threshold = int(visual_runtime_extreme_doc_page_threshold or 0)
        self.visual_runtime_office_text_layout_page_cap = int(visual_runtime_office_text_layout_page_cap or 0)
        self.visual_runtime_mixed_text_layout_page_cap = int(visual_runtime_mixed_text_layout_page_cap or 0)
        self.visual_runtime_extreme_doc_layout_page_cap = int(visual_runtime_extreme_doc_layout_page_cap or 0)
        self._normalize_text = normalize_text
        self._summarize_pdf_metadata_signals = summarize_pdf_metadata_signals
        self._classify_pdf_visual_profile = classify_pdf_visual_profile
        self._resolve_visual_runtime_limits = resolve_visual_runtime_limits

    def bootstrap(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reader: Any,
        page_count: int,
        layout_extractor: Any,
        source_cache_identity: str = "",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        native_page_count = max(1, min(int(page_count or 1), self.visual_first_max_pages, self.max_pages))
        probe_pages = min(native_page_count, max(3, self.visual_probe_pages))
        probe_chars = 0
        probe_text_parts: List[str] = []
        for page_idx in range(probe_pages):
            page_text = self._normalize_text(self._extract_page_text(reader=reader, page_idx=page_idx))
            probe_chars += len(page_text)
            if page_text:
                probe_text_parts.append(page_text[:1200])

        pdf_metadata_signals = self._summarize_pdf_metadata_signals(reader)
        pdf_profile = self._classify_pdf_visual_profile(
            file_name=file_name,
            page_count=native_page_count,
            probe_pages=probe_pages,
            probe_chars=probe_chars,
            probe_text="\n".join(probe_text_parts),
            pdf_metadata_signals=pdf_metadata_signals,
        )
        mineru_method = str(pdf_profile.get("method") or self.mineru_method or "auto").strip().lower() or "auto"
        mineru_method_reason = str(pdf_profile.get("reason") or "configured_default")
        mineru_method_fallbacks = list(pdf_profile.get("method_fallbacks") or [])
        stop_on_usable_text = bool(pdf_profile.get("stop_on_usable_text"))
        page_count_cap = int(pdf_profile.get("page_count_cap") or native_page_count)
        layout_page_count = min(native_page_count, max(1, page_count_cap))
        pdf_profile_name = str(pdf_profile.get("profile") or "").strip().lower()
        office_like = bool(pdf_profile.get("office_like"))
        if native_page_count >= self.visual_runtime_extreme_doc_page_threshold:
            if pdf_profile_name == "office_text_pdf":
                layout_page_count = min(layout_page_count, self.visual_runtime_office_text_layout_page_cap)
            elif pdf_profile_name == "mixed_text_pref_pdf":
                layout_page_count = min(layout_page_count, self.visual_runtime_mixed_text_layout_page_cap)
            elif office_like or Path(source_file_name or "").suffix.lower() == ".docx":
                layout_page_count = min(layout_page_count, self.visual_runtime_extreme_doc_layout_page_cap)

        layout_t0 = time.perf_counter()
        objects, mineru_page_lines = layout_extractor.extract_layout(
            pdf_bytes=file_bytes,
            file_name=file_name,
            start_page=1,
            end_page=layout_page_count,
            method=mineru_method,
            method_fallbacks=mineru_method_fallbacks,
            stop_on_usable_text=stop_on_usable_text,
            source_cache_identity=source_cache_identity,
        )
        layout_extract_ms = int((time.perf_counter() - layout_t0) * 1000)
        mineru_run_meta = self._get_layout_run_meta(layout_extractor)
        mineru_status = str(mineru_run_meta.get("status", "") or "").strip().lower()
        runtime_limits = self._resolve_visual_runtime_limits(
            file_name=file_name,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
            page_count=native_page_count,
            layout_page_count=layout_page_count,
            objects=objects,
        )
        runtime_limits["visual_pdf_profile"] = str(pdf_profile.get("profile") or "")
        runtime_limits["visual_pdf_office_like"] = bool(office_like)
        runtime_limits["visual_mineru_method"] = str(mineru_method or "")
        runtime_limits["visual_probe_chars"] = int(probe_chars)
        runtime_limits["visual_probe_pages"] = int(probe_pages)
        runtime_limits["visual_pdf_cue_hits"] = int(pdf_profile.get("visual_cue_hits", 0) or 0)
        visual_method_stats = {
            "visual_pdf_profile": str(pdf_profile.get("profile") or ""),
            "visual_probe_chars": int(probe_chars),
            "visual_probe_pages": int(probe_pages),
            "visual_probe_chars_per_page": float(pdf_profile.get("probe_chars_per_page") or 0.0),
            "visual_pdf_cue_hits": int(pdf_profile.get("visual_cue_hits", 0) or 0),
            "visual_pdf_metadata_signals": pdf_metadata_signals,
            "visual_mineru_method_requested": str(mineru_method or ""),
            "visual_mineru_method_reason": mineru_method_reason,
            "visual_mineru_method_fallbacks": list(mineru_method_fallbacks),
            "visual_text_only_short_circuit_enabled": bool(stop_on_usable_text),
            "visual_text_page_count": int(native_page_count),
            "visual_layout_page_count": int(layout_page_count),
        }
        return {
            "native_page_count": int(native_page_count),
            "probe_pages": int(probe_pages),
            "probe_chars": int(probe_chars),
            "pdf_metadata_signals": pdf_metadata_signals,
            "pdf_profile": pdf_profile,
            "layout_page_count": int(layout_page_count),
            "objects": list(objects or []),
            "mineru_page_lines": dict(mineru_page_lines or {}),
            "layout_extract_ms": int(layout_extract_ms),
            "mineru_run_meta": mineru_run_meta,
            "mineru_status": mineru_status,
            "runtime_limits": runtime_limits,
            "visual_method_stats": visual_method_stats,
        }

    @staticmethod
    def _extract_page_text(*, reader: Any, page_idx: int) -> str:
        try:
            return reader.pages[page_idx].extract_text() or ""
        except Exception:
            return ""

    @staticmethod
    def _get_layout_run_meta(layout_extractor: Any) -> Dict[str, Any]:
        try:
            meta = layout_extractor.get_last_run_meta()
        except Exception:
            return {}
        return dict(meta or {})
