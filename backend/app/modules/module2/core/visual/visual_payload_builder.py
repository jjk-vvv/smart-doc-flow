from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple


PageDimensions = Dict[int, Tuple[float, float]]
NormalizeText = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
ToFloatOrNone = Callable[[Any], Optional[float]]
AppendRef = Callable[[List[str], Dict[str, List[float]], str, str, List[float]], None]
LayoutBboxToRefBbox = Callable[..., List[float]]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
DecorateRowsWithMeta = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
ExtractHeadersFromTablePayload = Callable[[Dict[str, Any]], List[str]]
ExtractRowsFromTablePayload = Callable[[Dict[str, Any]], List[List[str]]]
MatrixFromHtmlTable = Callable[[str], List[List[str]]]
RecoverLowSignalHeaders = Callable[..., Tuple[List[str], List[Dict[str, Any]]]]
LooksLikeFalseTable = Callable[[List[str], List[Dict[str, Any]]], bool]
InferFigureType = Callable[[str], str]
FigureTextIsLowSignal = Callable[[str], bool]
NormalizeDataframeHeaders = Callable[..., List[str]]
NormalizeDataframeMatrix = Callable[..., List[List[str]]]
NormalizeFigureKeyValues = Callable[..., List[Dict[str, str]]]
CoerceFigureDataframe = Callable[..., Tuple[List[str], List[List[str]], str]]
RecoverFigureTitleAndCaption = Callable[..., Tuple[str, str]]
CountFigureMarkers = Callable[[str], int]


class VisualBboxRuntime:
    """Normalize raw layout bounding boxes into parser ref coordinates."""

    @staticmethod
    def normalize_ocr_box(box: object, width: int, height: int) -> Tuple[float, float, float, float]:
        if not isinstance(box, (list, tuple)) or not box:
            return 0.0, 0.0, 1.0, 1.0

        points: List[Tuple[float, float]] = []
        for point in box:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                points.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue

        if not points:
            return 0.0, 0.0, 1.0, 1.0

        x0 = max(0.0, min(point[0] for point in points)) / max(width, 1)
        y0 = max(0.0, min(point[1] for point in points)) / max(height, 1)
        x1 = max(0.0, max(point[0] for point in points)) / max(width, 1)
        y1 = max(0.0, max(point[1] for point in points)) / max(height, 1)
        return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)

    @staticmethod
    def layout_bbox_to_ref_bbox(
        *,
        page_no: int,
        raw_bbox: Any,
        page_dims: PageDimensions,
    ) -> List[float]:
        width, height = page_dims.get(page_no, (1.0, 1.0))
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return [float(page_no), 0.0, 0.0, 1.0, 1.0]
        try:
            x1, y1, x2, y2 = [float(raw_bbox[i]) for i in range(4)]
        except Exception:
            return [float(page_no), 0.0, 0.0, 1.0, 1.0]
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
            x1 *= width
            x2 *= width
            y1 *= height
            y2 *= height
        else:
            sx = 1.0
            sy = 1.0
            if x2 > width * 1.2 and x2 > 1:
                sx = width / float(x2)
            if y2 > height * 1.2 and y2 > 1:
                sy = height / float(y2)
            x1 *= sx
            x2 *= sx
            y1 *= sy
            y2 *= sy

        x1 = max(0.0, min(width, x1))
        x2 = max(0.0, min(width, x2))
        y1 = max(0.0, min(height, y1))
        y2 = max(0.0, min(height, y2))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        nx = x1 / width
        ny = y1 / height
        nw = max(0.0, (x2 - x1) / width)
        nh = max(0.0, (y2 - y1) / height)
        return [float(page_no), nx, ny, nw, nh]


class VisualTableBuilderRuntime:
    """Build table blocks for visual-first MinerU/Gemini payloads."""

    def __init__(
        self,
        *,
        visual_use_table_html_fallback: bool,
        table_max_cols: int,
        table_max_rows: int,
        table_cell_cap: int,
        ocr_table_min_rows: int,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        to_float_or_none: ToFloatOrNone,
        append_ref: AppendRef,
        layout_bbox_to_ref_bbox: LayoutBboxToRefBbox,
        build_header_meta: BuildHeaderMeta,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        extract_headers_from_table_payload: ExtractHeadersFromTablePayload,
        extract_rows_from_table_payload: ExtractRowsFromTablePayload,
        matrix_from_html_table: MatrixFromHtmlTable,
        recover_low_signal_headers: RecoverLowSignalHeaders,
        looks_like_false_table: LooksLikeFalseTable,
    ) -> None:
        self.visual_use_table_html_fallback = bool(visual_use_table_html_fallback)
        self.table_max_cols = max(1, int(table_max_cols or 1))
        self.table_max_rows = max(1, int(table_max_rows or 1))
        self.table_cell_cap = max(1, int(table_cell_cap or 1))
        self.ocr_table_min_rows = max(1, int(ocr_table_min_rows or 1))
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._to_float_or_none = to_float_or_none
        self._append_ref = append_ref
        self._layout_bbox_to_ref_bbox = layout_bbox_to_ref_bbox
        self._build_header_meta = build_header_meta
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._extract_headers_from_table_payload = extract_headers_from_table_payload
        self._extract_rows_from_table_payload = extract_rows_from_table_payload
        self._matrix_from_html_table = matrix_from_html_table
        self._recover_low_signal_headers = recover_low_signal_headers
        self._looks_like_false_table = looks_like_false_table

    def _build_table_block(
        self,
        *,
        table_id: str,
        source: str,
        page_no: int,
        headers: List[str],
        rows: List[Dict[str, Any]],
        confidence: float,
        caption: str,
        notes: List[str],
        item: Dict[str, Any],
        row_bbox: List[float],
    ) -> Dict[str, Any]:
        col_count = len(headers) if not rows else max((len(row.get("cells", [])) for row in rows), default=0)
        return {
            "table_id": table_id,
            "source": source,
            "page": page_no,
            "headers": headers,
            "header_meta": self._build_header_meta(headers),
            "rows": rows,
            "row_count": len(rows),
            "col_count": col_count,
            "quality": round(confidence, 4),
            "caption": caption,
            "notes": notes,
            "bbox_raw": item.get("bbox"),
            "bbox_norm": row_bbox,
            "image_path": str(item.get("img_path", "") or ""),
            "artifact_subtype": str(item.get("object_subtype", "") or item.get("source_object_type", "") or "table"),
            "source_object_type": str(item.get("source_object_type", "") or item.get("object_type", "") or "table"),
            "extraction_mode": "visual_first",
        }

    def build_table_from_visual_payload(
        self,
        *,
        table_id: str,
        page_no: int,
        payload: Dict[str, Any],
        item: Dict[str, Any],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        emitted_cells: int,
        source: str = "pdf_mineru_gemini",
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        headers = self._extract_headers_from_table_payload(payload)
        rows = self._extract_rows_from_table_payload(payload)
        caption = self._normalize_text(
            str(payload.get("caption") or payload.get("title") or " ".join(self._safe_text_list(item.get("caption"))))
        )
        notes = self._safe_text_list(payload.get("notes"), max_items=6, max_len=180)
        if not notes:
            notes = self._safe_text_list(item.get("footnote"), max_items=6, max_len=180)
        confidence = self._to_float_or_none(payload.get("confidence"))
        if confidence is None:
            confidence = 0.72
        confidence = max(0.1, min(1.0, float(confidence)))

        if not rows and self.visual_use_table_html_fallback:
            rows = self._matrix_from_html_table(str(item.get("table_body_html", "") or ""))
        if not headers and len(rows) >= 2:
            headers = rows[0]
            rows = rows[1:]
        if not headers and rows:
            max_cols = max(len(row) for row in rows)
            headers = [f"col_{idx}" for idx in range(1, max_cols + 1)]
        headers = [self._normalize_text(value) or f"col_{idx}" for idx, value in enumerate(headers, start=1)]
        row_bbox = self._layout_bbox_to_ref_bbox(page_no=page_no, raw_bbox=item.get("bbox"), page_dims=page_dims)
        if caption:
            self._append_ref(parts, bbox_map, f"{table_id}_caption", caption, row_bbox)
        for idx, note in enumerate(notes[:4], start=1):
            self._append_ref(parts, bbox_map, f"{table_id}_note{idx}", note, row_bbox)

        if not headers or not rows:
            return (
                self._build_table_block(
                    table_id=table_id,
                    source=source,
                    page_no=page_no,
                    headers=headers,
                    rows=[],
                    confidence=confidence,
                    caption=caption,
                    notes=notes,
                    item=item,
                    row_bbox=row_bbox,
                ),
                emitted_cells,
            )

        col_count = min(
            self.table_max_cols,
            max(len(headers), max((len(row) for row in rows), default=0)),
        )
        headers = (headers + [f"col_{idx}" for idx in range(len(headers) + 1, col_count + 1)])[:col_count]

        raw_rows_payload: List[Dict[str, Any]] = []
        row_index = 1
        for raw_row in rows[: self.table_max_rows]:
            cells_payload: List[Dict[str, Any]] = []
            for col_idx in range(1, col_count + 1):
                if emitted_cells >= self.table_cell_cap:
                    break
                text = self._normalize_text(str(raw_row[col_idx - 1] if col_idx - 1 < len(raw_row) else ""))
                if not text:
                    continue
                ref_id = f"{table_id}_r{row_index}_c{col_idx}"
                self._append_ref(parts, bbox_map, ref_id, text, row_bbox)
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": text,
                        "ref_id": ref_id,
                        "bbox": row_bbox,
                    }
                )
                emitted_cells += 1
            if cells_payload:
                raw_rows_payload.append({"row_index": row_index, "cells": cells_payload})
                row_index += 1
            if emitted_cells >= self.table_cell_cap:
                break

        headers, raw_rows_payload = self._recover_low_signal_headers(
            headers,
            raw_rows_payload,
            caption=caption,
            notes=notes,
        )

        if not raw_rows_payload:
            return (
                self._build_table_block(
                    table_id=table_id,
                    source=source,
                    page_no=page_no,
                    headers=headers,
                    rows=[],
                    confidence=confidence,
                    caption=caption,
                    notes=notes,
                    item=item,
                    row_bbox=row_bbox,
                ),
                emitted_cells,
            )

        data_rows = self._decorate_rows_with_meta(raw_rows_payload, headers)
        if len(data_rows) < self.ocr_table_min_rows:
            if len(data_rows) != 1:
                return (
                    self._build_table_block(
                        table_id=table_id,
                        source=source,
                        page_no=page_no,
                        headers=headers,
                        rows=data_rows,
                        confidence=confidence,
                        caption=caption,
                        notes=notes,
                        item=item,
                        row_bbox=row_bbox,
                    ),
                    emitted_cells,
                )
            first_cells = data_rows[0].get("cells", [])
            numeric_hits = sum(
                1
                for cell in first_cells
                if cell.get("numeric_value") is not None or re.search(r"\d", str(cell.get("text", "")))
            )
            if len(first_cells) < 3 or numeric_hits < 2:
                return (
                    self._build_table_block(
                        table_id=table_id,
                        source=source,
                        page_no=page_no,
                        headers=headers,
                        rows=data_rows,
                        confidence=confidence,
                        caption=caption,
                        notes=notes,
                        item=item,
                        row_bbox=row_bbox,
                    ),
                    emitted_cells,
                )
        if self._looks_like_false_table(headers, data_rows):
            return (
                self._build_table_block(
                    table_id=table_id,
                    source=source,
                    page_no=page_no,
                    headers=headers,
                    rows=data_rows,
                    confidence=confidence,
                    caption=caption,
                    notes=notes,
                    item=item,
                    row_bbox=row_bbox,
                ),
                emitted_cells,
            )

        return (
            self._build_table_block(
                table_id=table_id,
                source=source,
                page_no=page_no,
                headers=headers,
                rows=data_rows,
                confidence=confidence,
                caption=caption,
                notes=notes,
                item=item,
                row_bbox=row_bbox,
            ),
            emitted_cells,
        )


class VisualFigureBuilderRuntime:
    """Build figure blocks for visual-first MinerU/Gemini payloads."""

    def __init__(
        self,
        *,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        infer_figure_type_from_text: InferFigureType,
        figure_text_is_low_signal: FigureTextIsLowSignal,
        normalize_dataframe_headers: NormalizeDataframeHeaders,
        normalize_dataframe_matrix: NormalizeDataframeMatrix,
        normalize_figure_key_values: NormalizeFigureKeyValues,
        coerce_figure_dataframe: CoerceFigureDataframe,
        recover_figure_title_and_caption: RecoverFigureTitleAndCaption,
        count_figure_markers_in_text: CountFigureMarkers,
        to_float_or_none: ToFloatOrNone,
        append_ref: AppendRef,
        layout_bbox_to_ref_bbox: LayoutBboxToRefBbox,
    ) -> None:
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._infer_figure_type_from_text = infer_figure_type_from_text
        self._figure_text_is_low_signal = figure_text_is_low_signal
        self._normalize_dataframe_headers = normalize_dataframe_headers
        self._normalize_dataframe_matrix = normalize_dataframe_matrix
        self._normalize_figure_key_values = normalize_figure_key_values
        self._coerce_figure_dataframe = coerce_figure_dataframe
        self._recover_figure_title_and_caption = recover_figure_title_and_caption
        self._count_figure_markers_in_text = count_figure_markers_in_text
        self._to_float_or_none = to_float_or_none
        self._append_ref = append_ref
        self._layout_bbox_to_ref_bbox = layout_bbox_to_ref_bbox

    def build_figure_from_visual_payload(
        self,
        *,
        figure_id: str,
        page_no: int,
        payload: Dict[str, Any],
        item: Dict[str, Any],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        source: str = "pdf_mineru_gemini",
    ) -> Optional[Dict[str, Any]]:
        title = self._normalize_text(str(payload.get("title") or ""))
        caption = self._normalize_text(
            str(payload.get("caption") or payload.get("title") or " ".join(self._safe_text_list(item.get("caption"))))
        )
        figure_type = self._normalize_text(str(payload.get("type", "") or ""))
        if figure_type not in {"chart", "diagram", "formula", "photo", "other"}:
            figure_type = self._infer_figure_type_from_text(
                f"{title} {caption} {figure_type} {item.get('object_subtype', '')} {item.get('source_object_type', '')}"
            )
        axes = payload.get("axes")
        x_axis = ""
        y_axis = ""
        if isinstance(axes, dict):
            x_axis = self._normalize_text(str(axes.get("x", "") or ""))
            y_axis = self._normalize_text(str(axes.get("y", "") or ""))
        legend = self._safe_text_list(payload.get("legend"), max_items=8, max_len=120)
        insights = self._safe_text_list(payload.get("insights"), max_items=8, max_len=180)
        key_points = [value for value in insights if not self._figure_text_is_low_signal(value)]
        content_modes = [
            self._normalize_text(str(value or "")).lower()
            for value in (payload.get("content_modes") if isinstance(payload.get("content_modes"), list) else [])
        ]
        content_modes = [value for value in content_modes if value in {"dataframe", "topology", "text", "visual"}]
        if not content_modes:
            content_modes = ["visual"]

        dataframe = payload.get("dataframe") if isinstance(payload.get("dataframe"), dict) else {}
        df_headers = self._normalize_dataframe_headers(dataframe.get("headers"), max_len=120)
        df_rows = self._normalize_dataframe_matrix(dataframe.get("rows"), max_cell_len=160)

        topology = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
        topo_nodes_raw = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
        topo_edges_raw = topology.get("edges") if isinstance(topology.get("edges"), list) else []
        topo_nodes = [
            {
                "id": self._normalize_text(str(node.get("id", "") or "")),
                "label": self._normalize_text(str(node.get("label", "") or "")),
                "type": self._normalize_text(str(node.get("type", "") or "")),
            }
            for node in topo_nodes_raw[:20]
            if isinstance(node, dict)
        ]
        topo_edges = [
            {
                "source": self._normalize_text(str(edge.get("source", "") or "")),
                "target": self._normalize_text(str(edge.get("target", "") or "")),
                "label": self._normalize_text(str(edge.get("label", "") or "")),
            }
            for edge in topo_edges_raw[:30]
            if isinstance(edge, dict)
        ]
        text_blocks = [
            value
            for value in self._safe_text_list(payload.get("text_blocks"), max_items=10, max_len=180)
            if not self._figure_text_is_low_signal(value)
        ]
        key_values = self._normalize_figure_key_values(payload.get("key_values"), max_items=6)
        for item_raw in key_values:
            name = self._normalize_text(item_raw.get("name", ""))
            value = self._normalize_text(item_raw.get("value", ""))
            unit = self._normalize_text(item_raw.get("unit", ""))
            if unit:
                insights.append(f"{name}: {value} {unit}".strip())
            else:
                insights.append(f"{name}: {value}".strip())
        df_headers, df_rows, dataframe_source = self._coerce_figure_dataframe(
            headers=df_headers,
            rows=df_rows,
            key_values=key_values,
            fallback_texts=text_blocks + insights,
            caption_hint=caption or title,
            series_labels=legend,
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
            series_labels=legend,
            x_axis=x_axis,
            y_axis=y_axis,
        )
        if x_axis:
            insights.append(f"x-axis: {x_axis}")
        if y_axis:
            insights.append(f"y-axis: {y_axis}")
        for value in legend[:4]:
            insights.append(f"legend: {value}")
        for value in text_blocks[:3]:
            insights.append(f"text: {value}")
        if df_headers and df_rows:
            insights.append(f"dataframe: {len(df_rows)}x{max(len(row) for row in df_rows)}")
        if topo_nodes or topo_edges:
            insights.append(f"topology: nodes={len(topo_nodes)}, edges={len(topo_edges)}")
        if figure_type in {"", "other"} and (df_rows or key_values or legend or x_axis or y_axis):
            figure_type = "chart"
        if (df_headers and df_rows) and "dataframe" not in content_modes:
            content_modes.append("dataframe")
        if (topo_nodes or topo_edges) and "topology" not in content_modes:
            content_modes.append("topology")
        if text_blocks and "text" not in content_modes:
            content_modes.append("text")
        insights = [self._normalize_text(value) for value in insights if self._normalize_text(value)]
        if len(insights) > 8:
            insights = insights[:8]
        low_signal_only = not caption and not title and not df_rows and not key_values and not topo_nodes and not topo_edges
        if low_signal_only and not key_points and not text_blocks:
            return None
        ambiguous_caption = self._count_figure_markers_in_text(caption or title) > 1
        if ambiguous_caption and not df_rows and not key_values and not topo_nodes and not topo_edges:
            return None
        confidence = self._to_float_or_none(payload.get("confidence"))
        if confidence is None:
            confidence = 0.68
        confidence = max(0.1, min(1.0, float(confidence)))

        figure_bbox = self._layout_bbox_to_ref_bbox(page_no=page_no, raw_bbox=item.get("bbox"), page_dims=page_dims)
        ref_ids: List[str] = []
        if caption:
            cap_ref = f"{figure_id}_caption"
            self._append_ref(parts, bbox_map, cap_ref, caption, figure_bbox)
            ref_ids.append(cap_ref)
        for idx, insight in enumerate(insights[:6], start=1):
            ref_id = f"{figure_id}_k{idx}"
            self._append_ref(parts, bbox_map, ref_id, insight, figure_bbox)
            ref_ids.append(ref_id)
        return {
            "figure_id": figure_id,
            "source": source,
            "page": page_no,
            "figure_type": figure_type or "other",
            "title": title,
            "caption": caption,
            "insights": insights[:6],
            "key_points": key_points[:6] if key_points else insights[:6],
            "quality": round(confidence, 4),
            "ref_ids": ref_ids,
            "bbox_raw": item.get("bbox"),
            "bbox_norm": figure_bbox,
            "image_path": str(item.get("img_path", "") or ""),
            "artifact_subtype": str(item.get("object_subtype", "") or item.get("source_object_type", "") or "image"),
            "source_object_type": str(item.get("source_object_type", "") or item.get("object_type", "") or "image"),
            "content_modes": content_modes,
            "axes": {"x": x_axis, "y": y_axis},
            "legend": legend[:8],
            "key_values": key_values[:6],
            "dataframe": {
                "headers": df_headers,
                "rows": df_rows,
            },
            "dataframe_source": dataframe_source,
            "topology": {
                "nodes": topo_nodes[:20],
                "edges": topo_edges[:30],
            },
            "text_blocks": text_blocks[:8],
            "extraction_mode": "visual_first",
        }
