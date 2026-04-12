from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


LayoutObject = Dict[str, Any]
PageLines = Dict[int, List[str]]
TableBlocks = List[Dict[str, Any]]
VisualVisionJob = Dict[str, Any]
NormalizeText = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
InferFigureTypeFromText = Callable[[str], str]
ContainsMarker = Callable[[str], bool]
LooksLikeCueText = Callable[[str], bool]
LooksLikeFigureCueText = Callable[[str], bool]
BuildVisualObjectContext = Callable[..., Dict[str, Any]]
GetCropper = Callable[[], Any]


class VisualTableCueRuntime:
    """Detect table-like cue pages and judge whether native table output is weak."""

    def __init__(
        self,
        *,
        ocr_cue_max_pages: int,
        visual_weak_table_min: int,
        visual_weak_table_quality: float,
        normalize_text: Callable[[str], str],
    ) -> None:
        self.ocr_cue_max_pages = int(ocr_cue_max_pages or 0)
        self.visual_weak_table_min = int(visual_weak_table_min or 0)
        self.visual_weak_table_quality = float(visual_weak_table_quality or 0.0)
        self._normalize_text = normalize_text

    def collect_table_cue_pages(self, reader: Any, page_count: int) -> list[int]:
        limit = min(max(int(page_count or 0), 0), len(getattr(reader, "pages", [])))
        if limit <= 0:
            return []

        hits: list[int] = []
        for page_idx in range(limit):
            try:
                raw = reader.pages[page_idx].extract_text() or ""
            except Exception:
                continue
            text = self._normalize_text(raw)
            if not text:
                continue
            if self.looks_like_table_cue_text(text):
                hits.append(page_idx)

        if not hits:
            return []
        if self.ocr_cue_max_pages <= 0 or len(hits) <= self.ocr_cue_max_pages:
            return hits
        if self.ocr_cue_max_pages == 1:
            return [hits[len(hits) // 2]]

        step = (len(hits) - 1) / float(self.ocr_cue_max_pages - 1)
        sampled = [hits[int(round(i * step))] for i in range(self.ocr_cue_max_pages)]
        seen = set()
        out: list[int] = []
        for idx in sampled:
            if idx in seen:
                continue
            seen.add(idx)
            out.append(idx)
        return out

    @staticmethod
    def looks_like_table_cue_text(text: str) -> bool:
        t = str(text or "")
        if not t:
            return False
        cue_pattern = re.compile(
            r"\btable\b|\btab\.\b|list of tables|table of contents|\bannex\b|\bappendix\b|"
            r"\u9644\u8868|\u8868\s*[A-Za-z0-9\u4e00-\u9fa5]+",
            re.IGNORECASE,
        )
        return bool(cue_pattern.search(t))

    def is_weak_native_table_result(self, table_blocks: TableBlocks, cue_pages: list[int]) -> bool:
        cue_count = len(cue_pages or [])
        if not table_blocks:
            return cue_count > 0

        table_count = len(table_blocks)
        sources = {str(t.get("source", "")).strip().lower() for t in table_blocks}
        quality_vals: list[float] = []
        for table in table_blocks:
            try:
                quality_vals.append(float(table.get("quality")))
            except (TypeError, ValueError):
                continue
        avg_quality = (sum(quality_vals) / float(len(quality_vals))) if quality_vals else 0.0

        weak_by_count = table_count < self.visual_weak_table_min
        weak_by_quality = bool(quality_vals) and (avg_quality <= self.visual_weak_table_quality)
        fitz_only = bool(sources) and all(src == "pdf_fitz" for src in sources)

        if cue_count >= 20 and table_count <= max(2, self.visual_weak_table_min):
            return True
        if cue_count >= 8 and weak_by_count and fitz_only:
            return True
        if cue_count >= 8 and weak_by_quality and fitz_only:
            return True
        if cue_count >= 12 and weak_by_count and weak_by_quality:
            return True
        return False


class VisualPageSignalRuntime:
    """Choose Gemini vision target pages and derive page-level focus hints."""

    def __init__(
        self,
        *,
        gemini_vision_max_pages: int,
        gemini_vision_min_table_quality: float,
        gemini_vision_enable_figures: bool,
        looks_like_table_cue_text: LooksLikeCueText,
        looks_like_figure_cue_text: LooksLikeCueText,
        contains_figure_marker: ContainsMarker,
    ) -> None:
        self.gemini_vision_max_pages = max(0, int(gemini_vision_max_pages or 0))
        self.gemini_vision_min_table_quality = float(gemini_vision_min_table_quality or 0.0)
        self.gemini_vision_enable_figures = bool(gemini_vision_enable_figures)
        self._looks_like_table_cue_text = looks_like_table_cue_text
        self._looks_like_figure_cue_text = looks_like_figure_cue_text
        self._contains_figure_marker = contains_figure_marker

    def vision_focus_from_page_lines(self, lines: List[str]) -> str:
        cue_text = " ".join(str(line or "") for line in lines[:40])
        figure_hits = sum(1 for line in lines[:32] if self._contains_figure_marker(str(line or "")))
        figure_like = self._looks_like_figure_cue_text(cue_text) or figure_hits >= 2
        table_like = self._looks_like_table_cue_text(cue_text)
        if figure_like and not table_like:
            return "figure"
        if table_like and not figure_like:
            return "table"
        return "mixed"

    def select_low_quality_pages_for_vision(
        self,
        *,
        page_lines: PageLines,
        table_blocks: TableBlocks,
    ) -> List[int]:
        if not page_lines or self.gemini_vision_max_pages <= 0:
            return []

        pages = sorted(page_lines.keys())
        if not pages:
            return []

        vision_cap = self._resolve_vision_cap(pages=pages, page_lines=page_lines)
        quality_by_page = self._build_quality_by_page(table_blocks)

        ranked: List[Tuple[int, int, int]] = []
        page_signal: Dict[int, int] = {}
        for page_no in pages:
            lines = page_lines.get(page_no, [])
            if not lines:
                continue

            table_signal, figure_signal, combined_signal = self._score_page_signals(lines)
            page_signal[page_no] = combined_signal
            qv = quality_by_page.get(page_no)

            if qv is not None and qv < self.gemini_vision_min_table_quality:
                ranked.append((0, -combined_signal, page_no))
                continue

            if qv is None and table_signal >= 3:
                ranked.append((1, -combined_signal, page_no))
                continue

            if figure_signal >= 4:
                ranked.append((2, -combined_signal, page_no))
                continue

            if qv is not None and qv < (self.gemini_vision_min_table_quality + 0.10) and combined_signal >= 2:
                ranked.append((3, -combined_signal, page_no))

        if not ranked and len(table_blocks) < 2:
            for page_no in pages:
                lines = page_lines.get(page_no, [])
                signal = self._numeric_line_count(lines, limit=80) + (self._figure_marker_count(lines, limit=50) * 2)
                if signal >= 3:
                    ranked.append((4, -signal, page_no))

        if not ranked:
            if len(table_blocks) == 0 and len(pages) <= vision_cap:
                return pages
            if vision_cap == 1:
                return [pages[len(pages) // 2]]
            return self._sample_pages_evenly(pages, cap=vision_cap)

        ranked.sort()
        selected: List[int] = []
        selected_set = set()

        def _pick(page_no: int) -> None:
            if page_no in selected_set:
                return
            selected.append(page_no)
            selected_set.add(page_no)

        primary_cap = max(1, int(round(vision_cap * 0.55)))
        for _, _, page_no in ranked:
            _pick(page_no)
            if len(selected) >= primary_cap:
                break

        if len(selected) < vision_cap and len(pages) >= 8:
            seg_count = min(vision_cap, 8)
            for seg in range(seg_count):
                start = int(round((len(pages) * seg) / float(seg_count)))
                end = int(round((len(pages) * (seg + 1)) / float(seg_count)))
                seg_pages = pages[start:end] if end > start else []
                if not seg_pages:
                    continue
                best_page = max(seg_pages, key=lambda p: page_signal.get(p, 0))
                _pick(best_page)
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap and len(pages) >= 40:
            tail_len = max(10, len(pages) // 5)
            tail_pages = pages[-tail_len:]
            for page_no in sorted(tail_pages, key=lambda p: page_signal.get(p, 0), reverse=True):
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for page_no in list(selected):
                for cand in (page_no - 1, page_no + 1):
                    if cand in page_lines and page_signal.get(cand, 0) >= 2:
                        _pick(cand)
                        if len(selected) >= vision_cap:
                            break
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for _, _, page_no in ranked:
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for page_no in pages:
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        return selected

    def _resolve_vision_cap(self, *, pages: List[int], page_lines: PageLines) -> int:
        vision_cap = self.gemini_vision_max_pages
        probe_like_pages = 0
        for page_no in pages:
            lines = page_lines.get(page_no, [])
            joined = " ".join(lines[:3]).lower()
            if ("vision probe" in joined) or ("no extractable native text" in joined) or ("ocr found no text" in joined):
                probe_like_pages += 1

        if pages and (probe_like_pages / float(len(pages))) >= 0.55:
            return min(len(pages), max(vision_cap, min(48, len(pages))))
        if self.gemini_vision_enable_figures and len(pages) <= 60:
            return min(len(pages), max(vision_cap, min(36, len(pages))))
        return vision_cap

    @staticmethod
    def _build_quality_by_page(table_blocks: TableBlocks) -> Dict[int, float]:
        quality_by_page: Dict[int, float] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            if page_no <= 0:
                continue
            try:
                quality = float(table.get("quality"))
            except (TypeError, ValueError):
                quality = 0.66
            prev = quality_by_page.get(page_no)
            if prev is None:
                quality_by_page[page_no] = quality
            else:
                quality_by_page[page_no] = min(prev, quality)
        return quality_by_page

    def _score_page_signals(self, lines: List[str]) -> Tuple[int, int, int]:
        cue_text = " ".join(lines[:40])
        cue_hit = 1 if self._looks_like_table_cue_text(cue_text) else 0
        figure_hit = 1 if self._looks_like_figure_cue_text(cue_text) else 0
        table_signal = (4 if cue_hit else 0) + min(7, self._numeric_line_count(lines, limit=80))
        figure_signal = (5 if figure_hit else 0) + min(4, self._figure_marker_count(lines, limit=50))
        combined_signal = table_signal + figure_signal
        return table_signal, figure_signal, combined_signal

    @staticmethod
    def _numeric_line_count(lines: List[str], *, limit: int) -> int:
        numeric_lines = 0
        for line in lines[:limit]:
            if sum(1 for ch in str(line or "") if ch.isdigit()) >= 3:
                numeric_lines += 1
        return numeric_lines

    def _figure_marker_count(self, lines: List[str], *, limit: int) -> int:
        return sum(1 for line in lines[:limit] if self._contains_figure_marker(str(line or "")))

    @staticmethod
    def _sample_pages_evenly(pages: List[int], *, cap: int) -> List[int]:
        if not pages:
            return []
        if cap <= 0:
            return []
        if len(pages) <= cap:
            return pages
        if cap == 1:
            return [pages[len(pages) // 2]]
        step = (len(pages) - 1) / float(cap - 1)
        sampled = [pages[int(round(i * step))] for i in range(cap)]
        return sorted(set(sampled))


class VisualLayoutSelectorRuntime:
    """Select and prioritize visual layout objects for visual-first parsing."""

    def __init__(
        self,
        *,
        visual_max_objects: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_chart_score_min: int,
        visual_figure_cueless_fallback_max: int,
        visual_figure_chart_only: bool,
        visual_figure_allow_cueless_fallback: bool,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        infer_figure_type_from_text: InferFigureTypeFromText,
        contains_table_marker: ContainsMarker,
        contains_figure_marker: ContainsMarker,
        looks_like_figure_cue_text: LooksLikeFigureCueText,
    ) -> None:
        self.visual_max_objects = max(1, int(visual_max_objects or 1))
        self.visual_table_max_per_page = max(1, int(visual_table_max_per_page or 1))
        self.visual_figure_max_per_page = max(0, int(visual_figure_max_per_page or 0))
        self.visual_figure_chart_score_min = max(1, int(visual_figure_chart_score_min or 1))
        self.visual_figure_cueless_fallback_max = max(0, int(visual_figure_cueless_fallback_max or 0))
        self.visual_figure_chart_only = bool(visual_figure_chart_only)
        self.visual_figure_allow_cueless_fallback = bool(visual_figure_allow_cueless_fallback)
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._infer_figure_type_from_text = infer_figure_type_from_text
        self._contains_table_marker = contains_table_marker
        self._contains_figure_marker = contains_figure_marker
        self._looks_like_figure_cue_text = looks_like_figure_cue_text

    def prioritize_layout_objects(
        self,
        objects: List[LayoutObject],
        *,
        file_name: str,
        page_count: int,
        page_lines: PageLines,
        runtime_limits: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[LayoutObject], Dict[str, Any]]:
        runtime_limits = runtime_limits or {}
        max_objects = max(8, int(runtime_limits.get("max_objects", self.visual_max_objects) or self.visual_max_objects))
        table_max_per_page = max(
            1,
            int(runtime_limits.get("table_max_per_page", self.visual_table_max_per_page) or self.visual_table_max_per_page),
        )
        figure_max_per_page = max(
            0,
            int(runtime_limits.get("figure_max_per_page", self.visual_figure_max_per_page) or self.visual_figure_max_per_page),
        )
        chart_score_min = max(
            1,
            int(runtime_limits.get("chart_score_min", self.visual_figure_chart_score_min) or self.visual_figure_chart_score_min),
        )
        cueless_fallback_max = max(
            0,
            int(
                runtime_limits.get("cueless_fallback_max", self.visual_figure_cueless_fallback_max)
                or self.visual_figure_cueless_fallback_max
            ),
        )
        empty_summary = self._empty_selection_summary(chart_score_min=chart_score_min)
        if not objects:
            return [], empty_summary

        cleaned: List[Dict[str, Any]] = []
        for item in objects:
            obj_type = str(item.get("object_type", "") or "")
            if obj_type not in {"table", "image"}:
                continue
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0 or page_no > page_count:
                continue
            area = self._coerce_float(item.get("area", 0.0))
            cap_len = len(item.get("caption", [])) if isinstance(item.get("caption"), list) else 0
            figure_eval = None
            if obj_type == "image":
                figure_eval = self.evaluate_visual_figure_candidate(
                    file_name=file_name,
                    page_no=page_no,
                    item=item,
                    page_lines=page_lines,
                    chart_score_min=chart_score_min,
                )
            item_copy = dict(item)
            if isinstance(figure_eval, dict):
                item_copy["_visual_figure_eval"] = dict(figure_eval)
            cleaned.append(
                {
                    "item": item_copy,
                    "page_no": page_no,
                    "obj_type": obj_type,
                    "cap_len": cap_len,
                    "area": area,
                    "figure_eval": dict(figure_eval or {}),
                }
            )

        if not cleaned:
            return [], empty_summary

        summary = dict(empty_summary)
        table_candidates: List[Dict[str, Any]] = []
        figure_candidates: List[Dict[str, Any]] = []
        fallback_images: List[Dict[str, Any]] = []

        for candidate in cleaned:
            obj_type = str(candidate.get("obj_type", "") or "")
            if obj_type == "table":
                summary["visual_table_candidate_count_total"] = int(summary.get("visual_table_candidate_count_total", 0)) + 1
                table_candidates.append(candidate)
                continue

            summary["visual_figure_candidate_count_total"] = int(summary.get("visual_figure_candidate_count_total", 0)) + 1
            figure_eval = candidate.get("figure_eval") if isinstance(candidate.get("figure_eval"), dict) else {}
            chart_like = bool(figure_eval.get("chart_like"))
            keep_when_chart_only = bool(figure_eval.get("keep_when_chart_only"))
            if chart_like:
                summary["visual_figure_candidates_chart_like"] = int(summary.get("visual_figure_candidates_chart_like", 0)) + 1
            keep_candidate = chart_like or not self.visual_figure_chart_only or keep_when_chart_only
            if not keep_candidate:
                summary["visual_figure_candidates_filtered_nonchart"] = int(
                    summary.get("visual_figure_candidates_filtered_nonchart", 0)
                ) + 1
                if self.visual_figure_allow_cueless_fallback and cueless_fallback_max > 0:
                    fallback_images.append(candidate)
                continue
            summary["visual_figure_candidates_kept_by_rule"] = int(summary.get("visual_figure_candidates_kept_by_rule", 0)) + 1
            if figure_max_per_page > 0:
                figure_candidates.append(candidate)

        table_candidates.sort(key=lambda item: self.layout_selection_sort_key(item, for_global=False))
        figure_candidates.sort(key=lambda item: self.layout_selection_sort_key(item, for_global=False))

        selected = self.select_layout_candidates_with_page_coverage(
            tables=table_candidates,
            figures=figure_candidates,
            max_objects=max_objects,
            table_max_per_page=table_max_per_page,
            figure_max_per_page=figure_max_per_page,
        )

        if (
            self.visual_figure_chart_only
            and not any(str(item.get("object_type", "") or "") == "image" for item in selected)
            and self.visual_figure_allow_cueless_fallback
            and cueless_fallback_max > 0
        ):
            fallback_images.sort(key=lambda item: self.layout_selection_sort_key(item, for_global=True))
            fallback_used = 0
            fallback_count_by_page: Dict[int, int] = {}
            for fallback in fallback_images:
                if len(selected) >= max_objects:
                    break
                if fallback_used >= cueless_fallback_max:
                    break
                if figure_max_per_page <= 0:
                    break
                page_no = int(fallback.get("page_no", 0) or 0)
                fallback_count_by_page[page_no] = fallback_count_by_page.get(page_no, 0)
                if fallback_count_by_page[page_no] >= 1:
                    continue
                selected.append(dict(fallback.get("item") or {}))
                fallback_count_by_page[page_no] += 1
                fallback_used += 1
            summary["visual_figure_fallback_selected"] = fallback_used

        summary["visual_selected_table_candidates"] = sum(
            1 for item in selected if str(item.get("object_type", "") or "") == "table"
        )
        summary["visual_selected_figure_candidates"] = sum(
            1 for item in selected if str(item.get("object_type", "") or "") == "image"
        )
        summary["visual_selected_table_pages"] = len(
            {int(item.get("page", 0) or 0) for item in selected if str(item.get("object_type", "") or "") == "table"}
        )
        summary["visual_selected_figure_pages"] = len(
            {int(item.get("page", 0) or 0) for item in selected if str(item.get("object_type", "") or "") == "image"}
        )
        return selected, summary

    @staticmethod
    def layout_selection_sort_key(candidate: Dict[str, Any], *, for_global: bool) -> Tuple[Any, ...]:
        page_no = int(candidate.get("page_no", 0) or 0)
        obj_type = str(candidate.get("obj_type", "") or "")
        cap_len = int(candidate.get("cap_len", 0) or 0)
        area = float(candidate.get("area", 0.0) or 0.0)
        figure_eval = candidate.get("figure_eval") if isinstance(candidate.get("figure_eval"), dict) else {}
        selection_priority = int(figure_eval.get("selection_priority", 3) or 3)
        score = int(figure_eval.get("score", 0) or 0)
        if obj_type == "table":
            base = (-cap_len, -area)
        else:
            base = (selection_priority, -score, -cap_len, -area)
        if for_global:
            return base + (page_no,)
        return (page_no,) + base

    def select_layout_candidates_with_page_coverage(
        self,
        *,
        tables: List[Dict[str, Any]],
        figures: List[Dict[str, Any]],
        max_objects: int,
        table_max_per_page: int,
        figure_max_per_page: int,
    ) -> List[LayoutObject]:
        selected: List[LayoutObject] = []
        table_count_by_page: Dict[int, int] = {}
        figure_count_by_page: Dict[int, int] = {}
        table_pages: Dict[int, List[Dict[str, Any]]] = {}
        figure_pages: Dict[int, List[Dict[str, Any]]] = {}

        for candidate in tables:
            table_pages.setdefault(int(candidate.get("page_no", 0) or 0), []).append(candidate)
        for candidate in figures:
            figure_pages.setdefault(int(candidate.get("page_no", 0) or 0), []).append(candidate)

        def _push(candidate: Dict[str, Any]) -> bool:
            if len(selected) >= max_objects:
                return False
            obj_type = str(candidate.get("obj_type", "") or "")
            page_no = int(candidate.get("page_no", 0) or 0)
            if obj_type == "table":
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0)
                if table_count_by_page[page_no] >= table_max_per_page:
                    return False
                table_count_by_page[page_no] += 1
            else:
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0)
                if figure_count_by_page[page_no] >= figure_max_per_page:
                    return False
                figure_count_by_page[page_no] += 1
            selected.append(dict(candidate.get("item") or {}))
            return True

        coverage_pages = sorted(set(table_pages.keys()) | set(figure_pages.keys()))
        for page_no in coverage_pages:
            if len(selected) >= max_objects:
                break
            table_candidates = table_pages.get(page_no) or []
            if table_candidates:
                _push(table_candidates.pop(0))
            if len(selected) >= max_objects:
                break
            figure_candidates = figure_pages.get(page_no) or []
            if figure_candidates:
                _push(figure_candidates.pop(0))

        remaining_tables = sorted(
            [candidate for items in table_pages.values() for candidate in items],
            key=lambda item: self.layout_selection_sort_key(item, for_global=True),
        )
        for candidate in remaining_tables:
            if len(selected) >= max_objects:
                break
            _push(candidate)

        remaining_figures = sorted(
            [candidate for items in figure_pages.values() for candidate in items],
            key=lambda item: self.layout_selection_sort_key(item, for_global=True),
        )
        for candidate in remaining_figures:
            if len(selected) >= max_objects:
                break
            _push(candidate)

        return selected

    def evaluate_visual_figure_candidate(
        self,
        *,
        file_name: str,
        page_no: int,
        item: Dict[str, Any],
        page_lines: PageLines,
        chart_score_min: Optional[int] = None,
    ) -> Dict[str, Any]:
        artifact_subtype = self._normalize_text(
            str(item.get("object_subtype", "") or item.get("source_object_type", "") or "")
        )
        caption_text = self._normalize_text(
            " ".join(self._safe_text_list(item.get("caption"), max_items=4, max_len=200))
        )
        footnote_text = self._normalize_text(
            " ".join(self._safe_text_list(item.get("footnote"), max_items=4, max_len=180))
        )
        page_hint = ""
        if not caption_text and not footnote_text:
            page_hint = self._normalize_text(" ".join(page_lines.get(page_no, [])[:24]))
        cue_text = self._normalize_text(
            " ".join(part for part in [file_name, artifact_subtype, caption_text, footnote_text, page_hint] if part)
        )
        inferred_type = self._infer_figure_type_from_text(cue_text)
        score = 0
        reasons: List[str] = []
        table_like = bool(
            (caption_text and self._contains_table_marker(caption_text))
            or (cue_text and self._contains_table_marker(cue_text))
        )

        if caption_text and self._contains_figure_marker(caption_text):
            score += 3
            reasons.append("caption_marker")
        elif cue_text and self._contains_figure_marker(cue_text):
            score += 2
            reasons.append("context_marker")

        if caption_text and self._looks_like_figure_cue_text(caption_text):
            score += 3
            reasons.append("caption_cue")
        elif cue_text and self._looks_like_figure_cue_text(cue_text):
            score += 1
            reasons.append("context_cue")

        if artifact_subtype == "formula":
            score += 2
            reasons.append("subtype_formula")

        if table_like:
            score += 2
            reasons.append("table_marker")

        if inferred_type == "chart":
            score += 3
            reasons.append("type_chart")
        elif inferred_type == "diagram":
            score += 2
            reasons.append("type_diagram")
        elif inferred_type == "formula":
            score += 2
            reasons.append("type_formula")
        elif inferred_type == "photo" and caption_text:
            score += 1
            reasons.append("captioned_photo")

        if caption_text and re.search(r"\d{2,}", caption_text):
            score += 1
            reasons.append("caption_numeric")

        effective_score_min = max(1, int(chart_score_min or self.visual_figure_chart_score_min))
        chart_like = score >= effective_score_min or inferred_type in {"chart", "diagram"}
        keep_when_chart_only = bool(
            chart_like
            or inferred_type in {"diagram", "formula"}
            or table_like
            or (caption_text and self._contains_figure_marker(caption_text))
        )
        selection_priority = 3
        if chart_like:
            selection_priority = 0
        elif inferred_type in {"diagram", "formula"} or table_like:
            selection_priority = 1
        elif caption_text or footnote_text:
            selection_priority = 2
        return {
            "chart_like": bool(chart_like),
            "keep_when_chart_only": bool(keep_when_chart_only),
            "selection_priority": int(selection_priority),
            "score": int(score),
            "reasons": reasons[:6],
            "inferred_type": inferred_type,
            "table_like": bool(table_like),
            "artifact_subtype": artifact_subtype[:80],
            "chart_score_min": effective_score_min,
            "caption_text": caption_text[:240],
            "footnote_text": footnote_text[:240],
        }

    def _empty_selection_summary(self, *, chart_score_min: int) -> Dict[str, Any]:
        return {
            "visual_selected_table_candidates": 0,
            "visual_selected_figure_candidates": 0,
            "visual_table_candidate_count_total": 0,
            "visual_figure_candidate_count_total": 0,
            "visual_figure_candidates_kept_by_rule": 0,
            "visual_figure_candidates_chart_like": 0,
            "visual_figure_candidates_filtered_nonchart": 0,
            "visual_figure_fallback_selected": 0,
            "visual_selected_table_pages": 0,
            "visual_selected_figure_pages": 0,
            "visual_selection_strategy": "page_coverage_then_priority",
            "visual_figure_chart_only": bool(self.visual_figure_chart_only),
            "visual_figure_chart_score_min": int(chart_score_min),
        }

    @staticmethod
    def _coerce_float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0


class VisualObjectContextRuntime:
    """Build normalized visual object context and domain hints for vision jobs."""

    def __init__(
        self,
        *,
        visual_context_max_chars: int,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
    ) -> None:
        self.visual_context_max_chars = max(1, int(visual_context_max_chars or 1))
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list

    def build_visual_object_context(
        self,
        *,
        file_name: str,
        page_no: int,
        object_type: str,
        item: Dict[str, Any],
        page_lines: PageLines,
    ) -> Dict[str, Any]:
        caption = self._normalize_text(
            " ".join(self._safe_text_list(item.get("caption"), max_items=4, max_len=200))
        )
        page_text = " ".join(page_lines.get(page_no, [])[:90]).strip()
        if len(page_text) > self.visual_context_max_chars:
            page_text = page_text[: self.visual_context_max_chars]
        artifact_subtype = self._normalize_text(
            str(item.get("object_subtype", "") or item.get("source_object_type", "") or object_type)
        )
        domain_hints = self.infer_domain_hints(f"{file_name} {caption} {artifact_subtype} {page_text[:900]}")
        if artifact_subtype == "formula":
            domain_hints.extend(
                [
                    "Preserve mathematical and chemical notation exactly as shown.",
                    "Do not paraphrase formulas into prose when symbols are visible.",
                ]
            )
        return {
            "doc_name": file_name,
            "page": page_no,
            "object_type": object_type,
            "artifact_subtype": artifact_subtype or object_type,
            "caption_hint": caption,
            "footnote_hint": self._safe_text_list(item.get("footnote"), max_items=4, max_len=180),
            "nearby_text": page_text,
            "domain_hints": domain_hints,
        }

    def infer_domain_hints(self, text: str) -> List[str]:
        probe = self._normalize_text(text).lower()
        hints = [
            "Preserve table hierarchy and merged-header semantics.",
            "Do not fabricate missing cell values.",
            "Keep number formats and units exactly as shown.",
        ]
        if any(keyword in probe for keyword in ["compound", "chem", "cts", "reagent"]):
            hints.extend(
                [
                    "Keep chemical formulas verbatim, including parentheses and charge notation.",
                    "Do not split element symbols from subscripts/superscripts.",
                ]
            )
        if any(keyword in probe for keyword in ["nuclear", "fuel", "reactor", "isotope"]):
            hints.extend(
                [
                    "Preserve nuclide and isotope notation exactly.",
                    "Keep engineering symbols and scientific notation unchanged.",
                ]
            )
        if any(keyword in probe for keyword in ["gdp", "economic", "statistical", "bulletin"]):
            hints.extend(
                [
                    "Treat percentage, year-over-year, and unit columns as structured numeric fields.",
                    "Keep Chinese unit markers such as %, \u4e07, \u4ebf, \u5428 when present.",
                ]
            )
        return hints[:10]


class VisualJobPlannerRuntime:
    """Plan visual vision jobs from selected MinerU layout objects."""

    def __init__(
        self,
        *,
        build_visual_object_context: BuildVisualObjectContext,
        get_cropper: Optional[GetCropper] = None,
    ) -> None:
        self._build_visual_object_context = build_visual_object_context
        self._get_cropper = get_cropper

    def plan_jobs(
        self,
        *,
        selected_objects: List[LayoutObject],
        file_name: str,
        file_bytes: bytes,
        page_lines: PageLines,
        cropper: Any = None,
        runtime_figure_max_per_page: int,
        figure_refine_budget: int,
        figure_refine_min_score: int,
    ) -> Dict[str, Any]:
        cropper = cropper if cropper is not None else self._resolve_cropper()
        vision_jobs: List[VisualVisionJob] = []
        table_crop_ms = 0
        figure_crop_ms = 0
        vision_candidate_count = 0
        figure_refine_grants = 0
        remaining_figure_refine_budget = max(0, int(figure_refine_budget or 0))

        for item in selected_objects:
            obj_type = str(item.get("object_type", "") or "")
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0:
                continue

            if obj_type == "table":
                vision_candidate_count += 1

                crop_t0 = time.perf_counter()
                roi_bytes, roi_mime, _ = cropper.load_or_crop(item=item, pdf_bytes=file_bytes, is_table=True)
                table_crop_ms += int((time.perf_counter() - crop_t0) * 1000)
                if not roi_bytes:
                    continue
                context = self._build_visual_object_context(
                    file_name=file_name,
                    page_no=page_no,
                    object_type="table",
                    item=item,
                    page_lines=page_lines,
                )
                vision_jobs.append(
                    {
                        "index": len(vision_jobs),
                        "kind": "table",
                        "page_no": page_no,
                        "item": item,
                        "roi_bytes": roi_bytes,
                        "roi_mime": roi_mime,
                        "context": context,
                    }
                )
                continue

            if obj_type == "image" and runtime_figure_max_per_page > 0:
                vision_candidate_count += 1

                figure_eval = item.get("_visual_figure_eval") if isinstance(item.get("_visual_figure_eval"), dict) else {}
                figure_score = max(0, int(figure_eval.get("score", 0) or 0))
                allow_chart_refine = (
                    remaining_figure_refine_budget > 0
                    and figure_score >= int(figure_refine_min_score or 0)
                )
                if allow_chart_refine:
                    remaining_figure_refine_budget -= 1
                    figure_refine_grants += 1

                crop_t0 = time.perf_counter()
                roi_bytes, roi_mime, _ = cropper.load_or_crop(item=item, pdf_bytes=file_bytes, is_table=False)
                figure_crop_ms += int((time.perf_counter() - crop_t0) * 1000)
                if not roi_bytes:
                    continue
                context = self._build_visual_object_context(
                    file_name=file_name,
                    page_no=page_no,
                    object_type="figure",
                    item=item,
                    page_lines=page_lines,
                )
                vision_jobs.append(
                    {
                        "index": len(vision_jobs),
                        "kind": "figure",
                        "page_no": page_no,
                        "item": item,
                        "roi_bytes": roi_bytes,
                        "roi_mime": roi_mime,
                        "context": context,
                        "allow_refine": allow_chart_refine,
                    }
                )

        return {
            "vision_jobs": vision_jobs,
            "vision_candidate_count": int(vision_candidate_count),
            "table_crop_ms": int(table_crop_ms),
            "figure_crop_ms": int(figure_crop_ms),
            "figure_refine_grants": int(figure_refine_grants),
        }

    def _resolve_cropper(self) -> Any:
        if self._get_cropper is None:
            raise ValueError("cropper is required when get_cropper is not configured")
        return self._get_cropper()
