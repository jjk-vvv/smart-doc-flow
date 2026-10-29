from __future__ import annotations

from html import escape
from typing import Any, Callable, Dict, List, Optional, Tuple


FigureBlocks = List[Dict[str, Any]]
NormalizeText = Callable[[str], str]
InferFigureType = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
FigureTextIsLowSignal = Callable[[str], bool]
NormalizeDataframeHeaders = Callable[..., List[str]]
NormalizeDataframeMatrix = Callable[..., List[List[str]]]
NormalizeFigureKeyValues = Callable[..., List[Dict[str, str]]]
CoerceFigureDataframe = Callable[..., Tuple[List[str], List[List[str]], str]]
RecoverFigureTitleAndCaption = Callable[..., Tuple[str, str]]
ToFloatOrNone = Callable[[Any], Optional[float]]
CountFigureMarkers = Callable[[str], int]


class FigureVisionPayloadRuntime:
    def __init__(
        self,
        *,
        vision_enable_figures: bool,
        vision_max_figures_per_page: int,
        vision_min_figure_quality: float,
        normalize_text: NormalizeText,
        infer_figure_type_from_text: InferFigureType,
        safe_text_list: SafeTextList,
        figure_text_is_low_signal: FigureTextIsLowSignal,
        normalize_dataframe_headers: NormalizeDataframeHeaders,
        normalize_dataframe_matrix: NormalizeDataframeMatrix,
        normalize_figure_key_values: NormalizeFigureKeyValues,
        coerce_figure_dataframe: CoerceFigureDataframe,
        recover_figure_title_and_caption: RecoverFigureTitleAndCaption,
        to_float_or_none: ToFloatOrNone,
        count_figure_markers_in_text: CountFigureMarkers,
    ) -> None:
        self.vision_enable_figures = vision_enable_figures
        self.vision_max_figures_per_page = vision_max_figures_per_page
        self.vision_min_figure_quality = vision_min_figure_quality
        self._normalize_text = normalize_text
        self._infer_figure_type_from_text = infer_figure_type_from_text
        self._safe_text_list = safe_text_list
        self._figure_text_is_low_signal = figure_text_is_low_signal
        self._normalize_dataframe_headers = normalize_dataframe_headers
        self._normalize_dataframe_matrix = normalize_dataframe_matrix
        self._normalize_figure_key_values = normalize_figure_key_values
        self._coerce_figure_dataframe = coerce_figure_dataframe
        self._recover_figure_title_and_caption = recover_figure_title_and_caption
        self._to_float_or_none = to_float_or_none
        self._count_figure_markers_in_text = count_figure_markers_in_text

    def build_figures_from_vision_payload(
        self,
        payload: Dict[str, Any],
        page_no: int,
        figure_idx: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> Tuple[FigureBlocks, int]:
        if not self.vision_enable_figures or self.vision_max_figures_per_page <= 0:
            return [], figure_idx

        figures_raw = payload.get("figures", [])
        if not isinstance(figures_raw, list):
            return [], figure_idx

        built: FigureBlocks = []
        for figure_raw in figures_raw[: self.vision_max_figures_per_page]:
            if not isinstance(figure_raw, dict):
                continue

            title = self._normalize_text(str(figure_raw.get("title", "") or ""))
            caption = self._normalize_text(str(figure_raw.get("caption", "") or ""))
            kind = self._normalize_text(str(figure_raw.get("type", "") or ""))
            if not kind:
                kind = self._infer_figure_type_from_text(f"{title} {caption}")
            if kind not in {"chart", "diagram", "photo", "other"}:
                kind = self._infer_figure_type_from_text(kind)

            key_points = [
                item
                for item in self._safe_text_list(figure_raw.get("key_points"), max_items=8, max_len=180)
                if not self._figure_text_is_low_signal(item)
            ]
            legend_items = self._safe_text_list(figure_raw.get("legend"), max_items=8, max_len=80)
            text_blocks = [
                item
                for item in self._safe_text_list(figure_raw.get("text_blocks"), max_items=10, max_len=180)
                if not self._figure_text_is_low_signal(item)
            ]
            x_axis, y_axis = self._extract_axes(figure_raw.get("axes"))

            insights = self._build_insights(
                x_axis=x_axis,
                y_axis=y_axis,
                legend_items=legend_items,
                key_points=key_points,
                text_blocks=text_blocks,
            )

            dataframe = figure_raw.get("dataframe") if isinstance(figure_raw.get("dataframe"), dict) else {}
            df_headers = self._normalize_dataframe_headers(dataframe.get("headers"), max_len=120)
            df_rows = self._normalize_dataframe_matrix(dataframe.get("rows"), max_cell_len=160)
            key_values = self._normalize_figure_key_values(figure_raw.get("key_values"), max_items=6)
            for item in key_values:
                name = self._normalize_text(item.get("name", ""))
                value = self._normalize_text(item.get("value", ""))
                unit = self._normalize_text(item.get("unit", ""))
                if unit:
                    insights.append(f"{name}: {value} {unit}".strip())
                else:
                    insights.append(f"{name}: {value}".strip())

            df_headers, df_rows, dataframe_source = self._coerce_figure_dataframe(
                headers=df_headers,
                rows=df_rows,
                key_values=key_values,
                fallback_texts=text_blocks + key_points + insights,
                caption_hint=caption or title,
                series_labels=legend_items,
                x_axis=x_axis,
                y_axis=y_axis,
            )
            title, caption = self._recover_figure_title_and_caption(
                title=title,
                caption=caption,
                key_points=key_points,
                text_blocks=text_blocks,
                fallback_texts=insights,
                dataframe_headers=df_headers,
                series_labels=legend_items,
                x_axis=x_axis,
                y_axis=y_axis,
            )

            if df_headers and df_rows:
                insights.append(f"dataframe: {len(df_rows)}x{max(len(row) for row in df_rows)}")

            topo_nodes, topo_edges = self._normalize_topology(figure_raw.get("topology"))
            if topo_nodes or topo_edges:
                insights.append(f"topology: nodes={len(topo_nodes)}, edges={len(topo_edges)}")

            if kind in {"", "other"} and (df_rows or key_values or legend_items or x_axis or y_axis):
                kind = "chart"

            content_modes = self._normalize_content_modes(
                figure_raw.get("content_modes"),
                has_dataframe=bool(df_headers and df_rows),
                has_topology=bool(topo_nodes or topo_edges),
                has_text=bool(text_blocks),
            )
            insights = [item for item in insights if item]

            if not title and not caption and not insights and not df_rows and not key_values and not topo_nodes and not topo_edges:
                continue

            confidence = self._to_float_or_none(figure_raw.get("confidence"))
            if confidence is None:
                confidence = 0.72
            confidence = max(0.1, min(1.0, float(confidence)))
            if confidence < self.vision_min_figure_quality and not caption:
                continue
            if self._count_figure_markers_in_text(caption or title) > 1 and not df_rows and not key_values and not topo_nodes and not topo_edges:
                continue

            figure_id = f"{source_prefix}_f{figure_idx}"
            figure_idx += 1
            bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
            ref_ids: List[str] = []
            if caption:
                cap_ref = f"{figure_id}_caption"
                self._append_ref(parts, bbox_map, cap_ref, caption, bbox)
                ref_ids.append(cap_ref)
            for insight_idx, insight in enumerate(insights[:6], start=1):
                insight_ref = f"{figure_id}_k{insight_idx}"
                self._append_ref(parts, bbox_map, insight_ref, insight, bbox)
                ref_ids.append(insight_ref)

            built.append(
                {
                    "figure_id": figure_id,
                    "source": source_prefix,
                    "page": page_no,
                    "figure_type": kind or "other",
                    "title": title,
                    "caption": caption,
                    "insights": insights[:6],
                    "key_points": key_points[:6] if key_points else insights[:6],
                    "quality": round(confidence, 4),
                    "ref_ids": ref_ids,
                    "content_modes": content_modes[:4],
                    "axes": {"x": x_axis, "y": y_axis},
                    "legend": legend_items[:8],
                    "key_values": key_values[:6],
                    "dataframe": {
                        "headers": df_headers,
                        "rows": df_rows,
                    },
                    "dataframe_source": dataframe_source,
                    "topology": {
                        "nodes": topo_nodes,
                        "edges": topo_edges,
                    },
                    "text_blocks": text_blocks[:8],
                }
            )

        return built, figure_idx

    def _extract_axes(self, axes: Any) -> Tuple[str, str]:
        if not isinstance(axes, dict):
            return "", ""
        x_axis = self._normalize_text(str(axes.get("x", "") or ""))
        y_axis = self._normalize_text(str(axes.get("y", "") or ""))
        return x_axis, y_axis

    def _build_insights(
        self,
        *,
        x_axis: str,
        y_axis: str,
        legend_items: List[str],
        key_points: List[str],
        text_blocks: List[str],
    ) -> List[str]:
        insights: List[str] = []
        if x_axis:
            insights.append(f"x-axis: {x_axis}")
        if y_axis:
            insights.append(f"y-axis: {y_axis}")
        for item in legend_items:
            insights.append(f"legend: {self._normalize_text(item)}")
        for item in key_points:
            insights.append(self._normalize_text(item))
        for item in text_blocks[:3]:
            insights.append(f"text: {self._normalize_text(item)}")
        return insights

    def _normalize_topology(self, topology_raw: Any) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        topology = topology_raw if isinstance(topology_raw, dict) else {}
        topo_nodes_raw = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
        topo_edges_raw = topology.get("edges") if isinstance(topology.get("edges"), list) else []

        topo_nodes: List[Dict[str, str]] = []
        for node in topo_nodes_raw[:20]:
            if not isinstance(node, dict):
                continue
            topo_nodes.append(
                {
                    "id": self._normalize_text(str(node.get("id", "") or "")),
                    "label": self._normalize_text(str(node.get("label", "") or "")),
                    "type": self._normalize_text(str(node.get("type", "") or "")),
                }
            )

        topo_edges: List[Dict[str, str]] = []
        for edge in topo_edges_raw[:30]:
            if not isinstance(edge, dict):
                continue
            topo_edges.append(
                {
                    "source": self._normalize_text(str(edge.get("source", "") or "")),
                    "target": self._normalize_text(str(edge.get("target", "") or "")),
                    "label": self._normalize_text(str(edge.get("label", "") or "")),
                }
            )

        return topo_nodes, topo_edges

    def _normalize_content_modes(
        self,
        content_modes_raw: Any,
        *,
        has_dataframe: bool,
        has_topology: bool,
        has_text: bool,
    ) -> List[str]:
        content_modes = [
            self._normalize_text(str(item or "")).lower()
            for item in (content_modes_raw if isinstance(content_modes_raw, list) else [])
        ]
        content_modes = [item for item in content_modes if item in {"dataframe", "topology", "text", "visual"}]
        if has_dataframe and "dataframe" not in content_modes:
            content_modes.append("dataframe")
        if has_topology and "topology" not in content_modes:
            content_modes.append("topology")
        if has_text and "text" not in content_modes:
            content_modes.append("text")
        if not content_modes:
            content_modes = ["visual"]
        return content_modes

    @staticmethod
    def _append_ref(
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        ref_id: str,
        text: str,
        bbox: List[float],
    ) -> None:
        if ref_id not in bbox_map:
            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
            bbox_map[ref_id] = bbox
