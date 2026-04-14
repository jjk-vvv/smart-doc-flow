from __future__ import annotations

from html import escape
import re
from typing import Any, Callable, Dict, List, Tuple


FigureBlocks = List[Dict[str, Any]]
NormalizeText = Callable[[str], str]
NormalizeTokenForCompare = Callable[[str], str]
BoolTextFn = Callable[[str], bool]
StripFigureCaptionNoise = Callable[[str], str]
CountFigureMarkers = Callable[[str], int]
NextFigureIndex = Callable[[FigureBlocks, str], int]


class FigureInferenceRuntime:
    def __init__(
        self,
        *,
        gemini_vision_enable_figures: bool,
        normalize_text: NormalizeText,
        normalize_token_for_compare: NormalizeTokenForCompare,
        contains_figure_marker: BoolTextFn,
        contains_catalog_marker: BoolTextFn,
        strip_figure_caption_noise: StripFigureCaptionNoise,
        count_figure_markers_in_text: CountFigureMarkers,
        next_figure_index: NextFigureIndex,
    ) -> None:
        self.gemini_vision_enable_figures = gemini_vision_enable_figures
        self._normalize_text = normalize_text
        self._normalize_token_for_compare = normalize_token_for_compare
        self._contains_figure_marker = contains_figure_marker
        self._contains_catalog_marker = contains_catalog_marker
        self._strip_figure_caption_noise = strip_figure_caption_noise
        self._count_figure_markers_in_text = count_figure_markers_in_text
        self._next_figure_index = next_figure_index

    def looks_like_figure_cue_text(self, text: str) -> bool:
        probe = self._normalize_text(str(text or ""))
        if not probe:
            return False
        lower = probe.lower()
        if self._contains_figure_marker(probe):
            return True
        if any(
            keyword in lower
            for keyword in [
                "figure ",
                "chart",
                "diagram",
                "plot",
                "curve",
                "spectrum",
                "flowchart",
                "histogram",
            ]
        ):
            return True
        return any(keyword in probe for keyword in ["图表", "示意图", "流程图", "曲线", "趋势图", "柱状图", "折线图", "饼图"])

    def extract_figure_captions_from_lines(self, lines: List[str]) -> List[str]:
        captions: List[str] = []
        if not lines:
            return captions

        total = len(lines)
        for idx, raw in enumerate(lines):
            line = self._normalize_text(raw)
            if not line:
                continue

            lower = line.lower()
            if re.search(r"^\s*table\b", lower) or re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]+", line):
                continue

            marker_match = re.match(
                r"^\s*((?:fig(?:ure)?\.?\s*[A-Za-z0-9.\-]+|图\s*[0-9A-Za-z一二三四五六七八九十百千.\-]+))\s*[:：\-]?\s*(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if not marker_match:
                continue
            if re.search(r"\.{3,}\s*\d{1,4}\s*$", line):
                continue

            marker = self._normalize_text(marker_match.group(1))
            suffix = self._normalize_text(marker_match.group(2))
            caption = suffix
            if not caption and idx + 1 < total:
                next_line = self._normalize_text(lines[idx + 1])
                if next_line and not self._contains_figure_marker(next_line):
                    caption = next_line

            full = marker if not caption else f"{marker}: {caption}"
            full = self._normalize_text(full)
            if len(full) < 4:
                continue
            if len(full) > 220:
                full = full[:220]
            captions.append(full)

        deduped: List[str] = []
        seen = set()
        for caption in captions:
            key = self._normalize_token_for_compare(caption)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(caption)
        return deduped

    def infer_figure_type_from_text(self, text: str) -> str:
        probe = self._normalize_text(text).lower()
        if not probe:
            return "other"
        if any(keyword in probe for keyword in ["formula", "equation", "eq.", "公式", "方程", "化学式", "反应式"]):
            return "formula"
        if any(keyword in probe for keyword in ["diagram", "flow", "scheme", "示意", "流程", "框图"]):
            return "diagram"
        if any(
            keyword in probe
            for keyword in [
                "chart",
                "curve",
                "plot",
                "trend",
                "histogram",
                "bar",
                "line",
                "pie",
                "曲线",
                "趋势",
                "柱状",
                "折线",
                "饼图",
                "分布",
            ]
        ):
            return "chart"
        if any(keyword in probe for keyword in ["photo", "image", "照片", "图片"]):
            return "photo"
        return "other"

    def table_payload_has_content(self, payload: Dict[str, Any], *, table_max_cols: int) -> bool:
        if not isinstance(payload, dict):
            return False
        headers = payload.get("headers")
        rows = payload.get("rows")
        header_rows = payload.get("header_rows")
        if isinstance(headers, list) and any(str(item or "").strip() for item in headers):
            return True
        if isinstance(header_rows, list):
            for row in header_rows[:4]:
                if isinstance(row, list) and any(str(item or "").strip() for item in row):
                    return True
        if isinstance(rows, list):
            for row in rows[:6]:
                if isinstance(row, list) and any(str(item or "").strip() for item in row):
                    return True
                if isinstance(row, dict):
                    values = row.get("cells") if isinstance(row.get("cells"), list) else list(row.values())
                    if any(str(item or "").strip() for item in values[:table_max_cols]):
                        return True
        return any(str(payload.get(key) or "").strip() for key in ("caption", "title"))

    def figure_payload_has_content(self, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        for key in ("caption", "title", "type"):
            if str(payload.get(key) or "").strip():
                return True
        for key in ("legend", "insights", "text_blocks", "key_values"):
            values = payload.get(key)
            if isinstance(values, list) and any(str(item or "").strip() for item in values):
                return True
        dataframe = payload.get("dataframe")
        if isinstance(dataframe, dict):
            headers = dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else []
            rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
            if any(str(item or "").strip() for item in headers):
                return True
            for row in rows[:8]:
                if isinstance(row, list) and any(str(item or "").strip() for item in row):
                    return True
        topology = payload.get("topology")
        if isinstance(topology, dict):
            nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
            edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
            if nodes or edges:
                return True
        return False

    @staticmethod
    def safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values[:max_items]:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    def normalize_figure_key_values(self, values: Any, *, max_items: int = 8) -> List[Dict[str, str]]:
        if not isinstance(values, list):
            return []
        out: List[Dict[str, str]] = []
        for item in values[:max_items]:
            if not isinstance(item, dict):
                continue
            name = self._normalize_text(str(item.get("name", "") or ""))
            value = self._normalize_text(str(item.get("value", "") or ""))
            unit = self._normalize_text(str(item.get("unit", "") or ""))
            if not name and not value:
                continue
            out.append({"name": name, "value": value, "unit": unit})
        return out

    def infer_figures_from_page_lines(
        self,
        page_lines: Dict[int, List[str]],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
        existing_figure_blocks: FigureBlocks,
    ) -> FigureBlocks:
        if not page_lines:
            return []
        figure_idx = self._next_figure_index(existing_figure_blocks, f"{source_prefix}_f")
        figures: FigureBlocks = []
        for page_no in sorted(page_lines.keys()):
            lines = page_lines.get(page_no, [])
            page_probe = self._normalize_text(" ".join(lines[:24]))
            lower_probe = page_probe.lower()
            if (
                self._contains_catalog_marker(page_probe)
                or "list of figures" in lower_probe
                or "list of tables" in lower_probe
                or "table of contents" in lower_probe
            ):
                continue

            captions = self.extract_figure_captions_from_lines(lines)
            for caption in captions[:4]:
                figure_id = f"{source_prefix}_f{figure_idx}"
                figure_idx += 1
                ref_id = f"{figure_id}_caption"
                bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                if ref_id not in bbox_map:
                    parts.append(f'<ref id="{ref_id}">{escape(caption)}</ref>')
                    bbox_map[ref_id] = bbox
                figures.append(
                    {
                        "figure_id": figure_id,
                        "source": source_prefix,
                        "page": page_no,
                        "figure_type": self.infer_figure_type_from_text(caption),
                        "caption": caption,
                        "insights": [],
                        "quality": 0.58,
                        "ref_ids": [ref_id],
                    }
                )
        return self.merge_figure_blocks([], figures)

    def figure_has_structured_signal(self, item: Dict[str, Any]) -> bool:
        dataframe = item.get("dataframe") if isinstance(item.get("dataframe"), dict) else {}
        df_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        if any(isinstance(row, list) and any(str(cell or "").strip() for cell in row) for row in df_rows[:6]):
            return True
        key_values = item.get("key_values") if isinstance(item.get("key_values"), list) else []
        if key_values:
            return True
        legend = item.get("legend") if isinstance(item.get("legend"), list) else []
        if legend:
            return True
        axes = item.get("axes") if isinstance(item.get("axes"), dict) else {}
        if str(axes.get("x") or "").strip() or str(axes.get("y") or "").strip():
            return True
        topology = item.get("topology") if isinstance(item.get("topology"), dict) else {}
        nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
        edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
        return bool(nodes or edges)

    def figure_semantic_key(self, figure: Dict[str, Any]) -> str:
        title = self._normalize_text(str(figure.get("title", "") or ""))
        caption = self._normalize_text(str(figure.get("caption", "") or ""))
        semantic = self._strip_figure_caption_noise(title) or self._strip_figure_caption_noise(caption)
        if not semantic:
            return ""
        semantic = re.sub(r"\s+", "", semantic)
        return self._normalize_token_for_compare(semantic)

    def figure_deep_score(self, item: Dict[str, Any]) -> int:
        score = 0
        title = self._normalize_text(str(item.get("title", "") or ""))
        key_points = item.get("key_points") if isinstance(item.get("key_points"), list) else []
        insights = item.get("insights") if isinstance(item.get("insights"), list) else []
        text_blocks = item.get("text_blocks") if isinstance(item.get("text_blocks"), list) else []
        key_values = item.get("key_values") if isinstance(item.get("key_values"), list) else []
        dataframe = item.get("dataframe") if isinstance(item.get("dataframe"), dict) else {}
        df_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        if title:
            score += 1
        if key_points:
            score += min(3, len(key_points))
        if insights:
            score += min(2, len(insights))
        if text_blocks:
            score += 1
        if key_values:
            score += min(2, len(key_values))
        if df_rows:
            score += 4
        return score

    def figure_blocks_need_vision(self, figure_blocks: FigureBlocks) -> bool:
        if not self.gemini_vision_enable_figures or not figure_blocks:
            return False
        rich_count = sum(1 for item in figure_blocks if self.figure_deep_score(item) > 0)
        total = len(figure_blocks)
        if rich_count <= 0:
            return True
        rich_ratio = rich_count / float(total)
        if total <= 2:
            return rich_ratio < 1.0
        return rich_ratio < 0.4

    def merge_figure_blocks(self, left: FigureBlocks, right: FigureBlocks) -> FigureBlocks:
        if not left and not right:
            return []

        merged: Dict[Tuple[int, str], Dict[str, Any]] = {}
        passthrough: List[Dict[str, Any]] = []
        for figure in list(left) + list(right):
            page_no = int(figure.get("page", 0) or 0)
            caption = self._normalize_text(str(figure.get("caption", "") or ""))
            title = self._normalize_text(str(figure.get("title", "") or ""))
            key_norm = self._normalize_token_for_compare(caption or title)
            if key_norm:
                key = (page_no, key_norm[:96])
                prev = merged.get(key)
                prev_q = float(prev.get("quality", 0.0) or 0.0) if prev else -1.0
                cur_q = float(figure.get("quality", 0.0) or 0.0)
                if prev is None or cur_q >= prev_q:
                    merged[key] = dict(figure)
                continue
            passthrough.append(dict(figure))

        out = list(merged.values()) + passthrough
        semantic_groups: Dict[str, List[Dict[str, Any]]] = {}
        non_semantic_items: List[Dict[str, Any]] = []
        for item in out:
            semantic_key = self.figure_semantic_key(item)
            if not semantic_key:
                non_semantic_items.append(item)
                continue
            semantic_groups.setdefault(semantic_key, []).append(item)

        out = list(non_semantic_items)
        for _, items in semantic_groups.items():
            if len(items) <= 1:
                out.extend(items)
                continue
            ranked = sorted(
                items,
                key=lambda item: (
                    self.figure_deep_score(item),
                    1 if self.figure_has_structured_signal(item) else 0,
                    float(item.get("quality", 0.0) or 0.0),
                    len(self._normalize_text(str(item.get("caption", "") or ""))),
                ),
                reverse=True,
            )
            best = ranked[0]
            best_id = str(best.get("figure_id", "") or "")
            best_is_strong = self.figure_deep_score(best) >= 4 or self.figure_has_structured_signal(best)
            out.append(best)
            for item in ranked[1:]:
                if not best_is_strong:
                    out.append(item)
                    continue
                item_id = str(item.get("figure_id", "") or "")
                if item_id == best_id:
                    continue
                ambiguous_caption = self._count_figure_markers_in_text(str(item.get("caption", "") or "")) > 1
                weak_duplicate = self.figure_deep_score(item) <= 1 and not self.figure_has_structured_signal(item)
                if ambiguous_caption or weak_duplicate:
                    continue
                out.append(item)

        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for item in out:
            page_no = int(item.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(item)

        pruned: FigureBlocks = []
        for page_no in sorted(by_page.keys()):
            items = by_page.get(page_no, [])
            caption_items = [item for item in items if "_caption" in str(item.get("source", ""))]
            rich_items = [item for item in items if self.figure_deep_score(item) > 0]
            if rich_items:
                if caption_items:
                    caption_candidates = [str(item.get("caption") or "").strip() for item in caption_items if str(item.get("caption") or "").strip()]
                    first_caption = caption_candidates[0] if caption_candidates else ""
                    merged_rich: FigureBlocks = []
                    for item in rich_items:
                        candidate = dict(item)
                        if (not str(candidate.get("caption") or "").strip()) and first_caption:
                            candidate["caption"] = first_caption
                        merged_rich.append(candidate)
                    pruned.extend(merged_rich)
                else:
                    pruned.extend(rich_items)
                continue
            if caption_items:
                pruned.extend(caption_items)
                continue
            pruned.extend(items)
        pruned.sort(key=lambda item: (int(item.get("page", 0) or 0), str(item.get("figure_id", ""))))
        return pruned
