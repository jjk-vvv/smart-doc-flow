from __future__ import annotations

import hashlib
import io
import os
import re
import time
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from xml.etree import ElementTree as ET


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
NormalizeText = Callable[[str], str]
SafeTextList = Callable[..., List[str]]
BoolTextFn = Callable[[str], bool]
NormalizeDataframeHeaders = Callable[..., List[str]]
NormalizeDataframeMatrix = Callable[..., List[List[str]]]
DecorateRowsWithMeta = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
ParseImage = Callable[..., Tuple[str, Dict[str, List[float]], TableBlocks]]
GetLastFigureBlocks = Callable[[], FigureBlocks]
SetLastFigureBlocks = Callable[[FigureBlocks], None]


class DocxEnrichmentRuntime:
    """Extract DOCX chart XML and embedded media into figure/table enrichment artifacts."""

    def __init__(
        self,
        *,
        artifact_root_dir: Path,
        image_extensions: Set[str],
        docx_chart_xml_enable: bool,
        docx_media_probe_enable: bool,
        docx_media_max_assets: int,
        docx_media_vision_enable: bool,
        docx_media_nested_vision_enhance_enable: bool,
        docx_media_max_assets_unbounded: bool,
        docx_media_vision_max_assets: int,
        docx_media_vision_max_assets_unbounded: bool,
        docx_media_vision_max_bytes: int,
        docx_media_vision_chart_only: bool,
        docx_media_vision_allow_noncue: bool,
        nonpdf_figure_max: int,
        normalize_text: NormalizeText,
        safe_text_list: SafeTextList,
        looks_like_figure_cue_text: BoolTextFn,
        normalize_dataframe_headers: NormalizeDataframeHeaders,
        normalize_dataframe_matrix: NormalizeDataframeMatrix,
        decorate_rows_with_meta: DecorateRowsWithMeta,
        build_header_meta: BuildHeaderMeta,
        parse_image: ParseImage,
        get_last_figure_blocks: GetLastFigureBlocks,
        set_last_figure_blocks: SetLastFigureBlocks,
    ) -> None:
        self.artifact_root_dir = Path(artifact_root_dir).resolve()
        self.image_extensions = {str(item or "").lower() for item in image_extensions}
        self.docx_chart_xml_enable = bool(docx_chart_xml_enable)
        self.docx_media_probe_enable = bool(docx_media_probe_enable)
        self.docx_media_max_assets = max(0, int(docx_media_max_assets or 0))
        self.docx_media_vision_enable = bool(docx_media_vision_enable)
        self.docx_media_nested_vision_enhance_enable = bool(docx_media_nested_vision_enhance_enable)
        self.docx_media_max_assets_unbounded = bool(docx_media_max_assets_unbounded)
        self.docx_media_vision_max_assets = max(0, int(docx_media_vision_max_assets or 0))
        self.docx_media_vision_max_assets_unbounded = bool(docx_media_vision_max_assets_unbounded)
        self.docx_media_vision_max_bytes = max(0, int(docx_media_vision_max_bytes or 0))
        self.docx_media_vision_chart_only = bool(docx_media_vision_chart_only)
        self.docx_media_vision_allow_noncue = bool(docx_media_vision_allow_noncue)
        self.nonpdf_figure_max = int(nonpdf_figure_max or 0)
        self._normalize_text = normalize_text
        self._safe_text_list = safe_text_list
        self._looks_like_figure_cue_text = looks_like_figure_cue_text
        self._normalize_dataframe_headers = normalize_dataframe_headers
        self._normalize_dataframe_matrix = normalize_dataframe_matrix
        self._decorate_rows_with_meta = decorate_rows_with_meta
        self._build_header_meta = build_header_meta
        self._parse_image = parse_image
        self._get_last_figure_blocks = get_last_figure_blocks
        self._set_last_figure_blocks = set_last_figure_blocks

    def extract_docx_chart_xml_tables(self, file_bytes: bytes) -> Tuple[TableBlocks, Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "docx_chart_xml_seen": 0,
            "docx_chart_xml_parsed": 0,
            "docx_chart_xml_merged": 0,
        }
        if not self.docx_chart_xml_enable:
            return [], stats
        try:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        except Exception:
            return [], stats

        tables: TableBlocks = []
        with zf:
            chart_files = sorted(
                [name for name in zf.namelist() if name.startswith("word/charts/") and name.endswith(".xml")]
            )
            stats["docx_chart_xml_seen"] = len(chart_files)
            if not chart_files:
                return tables, stats

            ns = {
                "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
                "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            }
            chart_max_series = max(2, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_SERIES", "10")))
            chart_max_points = max(6, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_POINTS", "40")))
            chart_table_max_rows = max(24, int(os.getenv("MODULE2_DOCX_CHART_XML_TABLE_MAX_ROWS", "220")))
            for chart_idx, chart_path in enumerate(chart_files, start=1):
                try:
                    root = ET.fromstring(zf.read(chart_path))
                except Exception:
                    continue

                title_tokens = [
                    self._normalize_text(str(node.text or ""))
                    for node in root.findall(".//c:title//a:t", ns)
                ]
                title = self._normalize_text(" ".join(item for item in title_tokens if item))
                if not title:
                    title = f"DOCX图表 {chart_idx}"

                series_payload = self.extract_docx_chart_series_payload(
                    root=root,
                    ns=ns,
                    max_series=chart_max_series,
                    max_points=chart_max_points,
                )
                if not series_payload:
                    continue

                chart_table = self.build_docx_chart_table_block(
                    chart_idx=chart_idx,
                    title=title,
                    series_payload=series_payload,
                    parts=[],
                    bbox_map={},
                    max_rows=chart_table_max_rows,
                )
                if not chart_table:
                    continue
                tables.append(chart_table)
                stats["docx_chart_xml_parsed"] = int(stats.get("docx_chart_xml_parsed", 0) or 0) + 1
        return tables, stats

    def collect_docx_chart_points(
        self,
        ser: ET.Element,
        ns: Dict[str, str],
        node_paths: List[str],
        max_points: int,
    ) -> List[str]:
        points: List[str] = []
        limit = max(1, int(max_points or 1))
        for node_path in node_paths:
            for node in ser.findall(f".//{node_path}//c:v", ns) + ser.findall(f".//{node_path}//a:t", ns):
                text = self._normalize_text(str(node.text or ""))
                if not text:
                    continue
                if points and points[-1] == text:
                    continue
                points.append(text)
                if len(points) >= limit:
                    return points
        return points

    def extract_docx_chart_series_payload(
        self,
        *,
        root: ET.Element,
        ns: Dict[str, str],
        max_series: int,
        max_points: int,
    ) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        series_nodes = root.findall(".//c:ser", ns)
        for series_idx, ser in enumerate(series_nodes[: max(1, max_series)], start=1):
            name_tokens = [
                self._normalize_text(str(node.text or ""))
                for node in (ser.findall(".//c:tx//c:v", ns) + ser.findall(".//c:tx//a:t", ns))
            ]
            series_name = self._normalize_text(" ".join(item for item in name_tokens if item))
            if not series_name:
                series_name = f"序列{series_idx}"

            categories = self.collect_docx_chart_points(ser, ns, ["c:cat", "c:xVal"], max_points=max_points)
            values = self.collect_docx_chart_points(ser, ns, ["c:val", "c:yVal", "c:bubbleSize"], max_points=max_points)

            if not categories and values:
                categories = [f"点{idx + 1}" for idx in range(len(values))]
            if not values and not categories:
                continue
            payload.append(
                {
                    "name": series_name,
                    "categories": categories[:max_points],
                    "values": values[:max_points],
                }
            )
        return payload

    def build_docx_chart_key_points(self, *, series_payload: List[Dict[str, Any]], max_items: int) -> List[str]:
        key_points: List[str] = []
        for item in series_payload:
            series_name = self._normalize_text(str(item.get("name") or "序列"))
            categories = [self._normalize_text(str(value or "")) for value in (item.get("categories") or [])]
            values = [self._normalize_text(str(value or "")) for value in (item.get("values") or [])]
            categories = [value for value in categories if value]
            values = [value for value in values if value]
            if values and categories:
                paired = ", ".join(f"{categories[idx]}={values[idx]}" for idx in range(min(4, len(categories), len(values))))
                text = f"{series_name}: {paired}"
            elif values:
                text = f"{series_name}: {', '.join(values[:4])}"
            elif categories:
                text = f"{series_name}: {', '.join(categories[:4])}"
            else:
                continue
            text = self._normalize_text(text)
            if text:
                key_points.append(text)
            if len(key_points) >= max(1, int(max_items or 1)):
                break
        return key_points

    def build_docx_chart_table_block(
        self,
        *,
        chart_idx: int,
        title: str,
        series_payload: List[Dict[str, Any]],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        max_rows: int,
    ) -> Optional[Dict[str, Any]]:
        if not series_payload:
            return None

        headers = ["序列", "类别", "数值"]
        rows_payload: List[Dict[str, Any]] = []
        row_idx = 1
        limit = max(12, int(max_rows or 12))

        for series_idx, item in enumerate(series_payload, start=1):
            series_name = self._normalize_text(str(item.get("name") or f"序列{series_idx}"))
            categories = [self._normalize_text(str(value or "")) for value in (item.get("categories") or [])]
            values = [self._normalize_text(str(value or "")) for value in (item.get("values") or [])]
            point_count = max(len(categories), len(values))
            if point_count <= 0:
                continue
            for point_idx in range(point_count):
                if len(rows_payload) >= limit:
                    break
                category = categories[point_idx] if point_idx < len(categories) and categories[point_idx] else f"点{point_idx + 1}"
                value = values[point_idx] if point_idx < len(values) else ""
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell_text in enumerate([series_name, category, value], start=1):
                    normalized = self._normalize_text(str(cell_text or ""))
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if normalized:
                        cell_ref = f"docx_chart_t{chart_idx}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(normalized)}</ref>')
                        bbox_map[cell_ref] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": normalized,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                if any(str(cell.get("text", "")).strip() for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                    row_idx += 1
            if len(rows_payload) >= limit:
                break

        if not rows_payload:
            return None

        decorated_rows = self._decorate_rows_with_meta(rows_payload, headers)
        if not decorated_rows:
            return None

        return {
            "table_id": f"docx_chart_t{chart_idx}",
            "source": "docx_chart_xml",
            "page": 1,
            "headers": headers,
            "header_meta": self._build_header_meta(headers),
            "rows": decorated_rows,
            "row_count": len(decorated_rows),
            "col_count": max((len(row.get("cells", [])) for row in decorated_rows), default=0),
            "chart_title": self._normalize_text(title),
        }

    def extract_docx_chart_and_media(
        self,
        file_bytes: bytes,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        start_ref_idx: int,
    ) -> Tuple[FigureBlocks, TableBlocks, Dict[str, Any], int]:
        figures: FigureBlocks = []
        table_blocks: TableBlocks = []
        stats: Dict[str, Any] = {
            "docx_chart_xml_seen": 0,
            "docx_chart_xml_parsed": 0,
            "docx_chart_xml_elapsed_ms": 0,
            "docx_media_seen": 0,
            "docx_media_used": 0,
            "docx_media_parsed": 0,
            "docx_media_parse_errors": 0,
            "docx_media_skipped_duplicate": 0,
            "docx_media_probe_elapsed_ms": 0,
            "docx_media_vision_elapsed_ms": 0,
            "docx_media_vision_attempted": 0,
            "docx_media_fallback_count": 0,
            "docx_media_vision_enabled": bool(self.docx_media_vision_enable),
            "docx_media_nested_vision_enhance_enabled": bool(self.docx_media_nested_vision_enhance_enable),
            "docx_media_max_assets_unbounded": bool(self.docx_media_max_assets_unbounded),
            "docx_media_vision_max_assets_unbounded": bool(self.docx_media_vision_max_assets_unbounded),
        }
        ref_idx = start_ref_idx
        if not (self.docx_chart_xml_enable or self.docx_media_probe_enable):
            return figures, table_blocks, stats, ref_idx

        try:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        except Exception:
            return figures, table_blocks, stats, ref_idx

        with zf:
            names = zf.namelist()
            chart_files = sorted(
                [name for name in names if name.startswith("word/charts/") and name.endswith(".xml")]
            )
            stats["docx_chart_xml_seen"] = len(chart_files)

            if self.docx_chart_xml_enable and chart_files:
                chart_t0 = time.perf_counter()
                ns = {
                    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
                    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                }
                chart_max_series = max(2, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_SERIES", "10")))
                chart_max_points = max(6, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_POINTS", "40")))
                chart_max_key_points = max(4, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_KEYPOINTS", "12")))
                chart_table_max_rows = max(24, int(os.getenv("MODULE2_DOCX_CHART_XML_TABLE_MAX_ROWS", "220")))
                stats["docx_chart_xml_table_count"] = 0
                for chart_idx, chart_path in enumerate(chart_files, start=1):
                    if self.nonpdf_figure_max > 0 and len(figures) >= self.nonpdf_figure_max:
                        break
                    try:
                        root = ET.fromstring(zf.read(chart_path))
                    except Exception:
                        continue

                    title_tokens = [
                        self._normalize_text(str(node.text or ""))
                        for node in root.findall(".//c:title//a:t", ns)
                    ]
                    title = self._normalize_text(" ".join(item for item in title_tokens if item))
                    if not title:
                        title = f"DOCX图表 {chart_idx}"

                    series_payload = self.extract_docx_chart_series_payload(
                        root=root,
                        ns=ns,
                        max_series=chart_max_series,
                        max_points=chart_max_points,
                    )
                    key_points = self.build_docx_chart_key_points(
                        series_payload=series_payload,
                        max_items=chart_max_key_points,
                    )

                    summary = f"{title}。"
                    if key_points:
                        summary += " 关键数据：" + "；".join(key_points[:6])

                    ref_id = f"docx_chart_{chart_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(summary)}</ref>')
                    bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

                    figures.append(
                        {
                            "figure_id": f"docx_chart_f{chart_idx}",
                            "source": "docx_chart_xml",
                            "page": 1,
                            "figure_type": "chart",
                            "caption": title,
                            "key_points": key_points,
                            "quality": 0.9,
                            "ref_ids": [ref_id],
                            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                        }
                    )
                    chart_table = self.build_docx_chart_table_block(
                        chart_idx=chart_idx,
                        title=title,
                        series_payload=series_payload,
                        parts=parts,
                        bbox_map=bbox_map,
                        max_rows=chart_table_max_rows,
                    )
                    if chart_table:
                        table_blocks.append(chart_table)
                        stats["docx_chart_xml_table_count"] = int(stats.get("docx_chart_xml_table_count", 0) or 0) + 1
                    stats["docx_chart_xml_parsed"] += 1
                stats["docx_chart_xml_elapsed_ms"] = int((time.perf_counter() - chart_t0) * 1000)

            media_files_all = sorted(
                [
                    name
                    for name in names
                    if name.startswith("word/media/")
                    and os.path.splitext(name.lower())[1] in self.image_extensions
                ]
            )
            stats["docx_media_seen"] = len(media_files_all)
            if self.docx_media_probe_enable and self.docx_media_max_assets > 0 and media_files_all:
                media_t0 = time.perf_counter()
                media_candidates: List[Dict[str, Any]] = []
                for media_path in media_files_all:
                    media_name = os.path.basename(media_path)
                    media_size = 0
                    try:
                        media_size = max(0, int(zf.getinfo(media_path).file_size))
                    except Exception:
                        media_size = 0
                    media_candidates.append(
                        {
                            "path": media_path,
                            "name": media_name,
                            "size": media_size,
                            "is_chart_cue": bool(self._looks_like_figure_cue_text(media_name)),
                        }
                    )

                chart_cue_seen = sum(1 for item in media_candidates if bool(item.get("is_chart_cue")))
                stats["docx_media_chart_cue_seen"] = int(chart_cue_seen)
                media_candidates.sort(
                    key=lambda item: (
                        0 if bool(item.get("is_chart_cue")) else 1,
                        -int(item.get("size") or 0),
                        str(item.get("path") or ""),
                    )
                )
                media_files = media_candidates[: self.docx_media_max_assets]
                stats["docx_media_selected"] = len(media_files)
                stats["docx_media_selected_strategy"] = "chart_cue_then_size"

                allow_noncue_vision_fallback = bool(
                    self.docx_media_vision_chart_only
                    and chart_cue_seen == 0
                    and self.docx_media_vision_allow_noncue
                )
                stats["docx_media_vision_noncue_fallback"] = bool(allow_noncue_vision_fallback)

                seen_sha256: set[str] = set()
                vision_attempted = 0
                saved_last_figures = self._get_last_figure_blocks()
                for media_idx, media_item in enumerate(media_files, start=1):
                    if self.nonpdf_figure_max > 0 and len(figures) >= self.nonpdf_figure_max:
                        break
                    media_path = str(media_item.get("path") or "")
                    media_name = str(media_item.get("name") or os.path.basename(media_path))
                    media_type = "chart" if bool(media_item.get("is_chart_cue")) else "photo"
                    caption = f"DOCX内嵌图像 {media_name}"
                    try:
                        media_bytes = zf.read(media_path)
                    except Exception:
                        media_bytes = b""
                    media_size = len(media_bytes)
                    artifact_path = self.persist_docx_media_artifact(
                        media_bytes=media_bytes,
                        media_name=media_name,
                        media_idx=media_idx,
                    )
                    if media_bytes:
                        media_sha = hashlib.sha256(media_bytes).hexdigest()
                        if media_sha in seen_sha256:
                            stats["docx_media_skipped_duplicate"] += 1
                            continue
                        seen_sha256.add(media_sha)
                    parsed_from_media = False
                    if (
                        self.docx_media_vision_enable
                        and media_bytes
                        and media_size <= self.docx_media_vision_max_bytes
                        and vision_attempted < self.docx_media_vision_max_assets
                        and (
                            (not self.docx_media_vision_chart_only)
                            or (media_type == "chart")
                            or allow_noncue_vision_fallback
                        )
                    ):
                        vision_attempted += 1
                        stats["docx_media_vision_attempted"] = int(vision_attempted)
                        vision_asset_t0 = time.perf_counter()
                        try:
                            _vision_md, _vision_bbox, _vision_tables = self._parse_image(
                                file_name=media_name,
                                file_bytes=media_bytes,
                                enable_vision_enhance=self.docx_media_nested_vision_enhance_enable,
                            )
                            vision_figures = self._get_last_figure_blocks()
                            if _vision_tables:
                                for t_idx, table in enumerate(_vision_tables[:2], start=1):
                                    copied = dict(table)
                                    copied["table_id"] = f"docx_media_t{media_idx}_{t_idx}"
                                    copied["source"] = "docx_media_vision"
                                    copied["page"] = 1
                                    copied["artifact_path"] = artifact_path or copied.get("artifact_path")
                                    table_blocks.append(copied)
                            if vision_figures:
                                best = max(
                                    vision_figures,
                                    key=lambda item: float(item.get("quality", 0.0) or 0.0),
                                )
                                normalized_media_figure = self._normalize_docx_media_vision_figure(
                                    best=best,
                                    media_idx=media_idx,
                                    media_type=media_type,
                                    caption=caption,
                                    artifact_path=artifact_path,
                                )
                                ref_id = f"docx_media_{media_idx}_vision"
                                summary = str(normalized_media_figure.get("caption") or caption)
                                points = self._safe_text_list(
                                    normalized_media_figure.get("key_points"),
                                    max_items=6,
                                    max_len=160,
                                )
                                if points:
                                    summary = f"{summary}；" + "；".join(points[:3])
                                parts.append(f'<ref id="{ref_id}">{escape(summary)}</ref>')
                                bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
                                normalized_media_figure["ref_ids"] = [ref_id]
                                figures.append(normalized_media_figure)
                                stats["docx_media_used"] += 1
                                stats["docx_media_parsed"] += 1
                                ref_idx += 1
                                parsed_from_media = True
                        except Exception:
                            stats["docx_media_parse_errors"] += 1
                        finally:
                            stats["docx_media_vision_elapsed_ms"] = int(
                                int(stats.get("docx_media_vision_elapsed_ms", 0) or 0)
                                + ((time.perf_counter() - vision_asset_t0) * 1000)
                            )
                            self._set_last_figure_blocks(saved_last_figures)
                    if parsed_from_media:
                        continue

                    ref_id = f"docx_media_{media_idx}"
                    probe_text = f"{caption}（大小 {round(media_size / 1024.0, 1)}KB）"
                    parts.append(f'<ref id="{ref_id}">{escape(probe_text)}</ref>')
                    bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

                    figures.append(
                        {
                            "figure_id": f"docx_media_f{media_idx}",
                            "source": "docx_media",
                            "page": 1,
                            "figure_type": media_type,
                            "caption": caption,
                            "key_points": [probe_text],
                            "quality": 0.6,
                            "ref_ids": [ref_id],
                            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                            "artifact_path": artifact_path,
                        }
                    )
                    stats["docx_media_used"] += 1
                    stats["docx_media_fallback_count"] += 1
                    ref_idx += 1
                stats["docx_media_probe_elapsed_ms"] = int((time.perf_counter() - media_t0) * 1000)

        return figures, table_blocks, stats, ref_idx

    def persist_docx_media_artifact(
        self,
        *,
        media_bytes: bytes,
        media_name: str,
        media_idx: int,
    ) -> str:
        if not media_bytes:
            return ""
        ext = Path(media_name or "").suffix.lower()
        if ext not in self.image_extensions:
            ext = ".png"
        safe_stem = re.sub(r"[^a-zA-Z0-9_\-]+", "_", Path(media_name or "").stem or f"media_{media_idx}")
        digest = hashlib.sha256(media_bytes).hexdigest()[:16]
        rel = Path("docx_media") / f"{safe_stem}_{media_idx}_{digest}{ext}"
        target = (self.artifact_root_dir / rel).resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(media_bytes)
            return str(target)
        except Exception:
            return ""

    def _normalize_docx_media_vision_figure(
        self,
        *,
        best: Dict[str, Any],
        media_idx: int,
        media_type: str,
        caption: str,
        artifact_path: str,
    ) -> Dict[str, Any]:
        best_caption = self._normalize_text(str(best.get("caption", "") or "")) or caption
        points = self._safe_text_list(best.get("key_points") or best.get("insights"), max_items=6, max_len=160)
        content_modes = [
            self._normalize_text(str(item or "")).lower()
            for item in (best.get("content_modes") if isinstance(best.get("content_modes"), list) else [])
        ]
        content_modes = [item for item in content_modes if item in {"dataframe", "topology", "text", "visual"}]
        dataframe_raw = best.get("dataframe") if isinstance(best.get("dataframe"), dict) else {}
        df_headers = self._normalize_dataframe_headers(dataframe_raw.get("headers"), max_len=120)
        df_rows = self._normalize_dataframe_matrix(dataframe_raw.get("rows"), max_cell_len=160)
        topology_raw = best.get("topology") if isinstance(best.get("topology"), dict) else {}
        topo_nodes_raw = topology_raw.get("nodes") if isinstance(topology_raw.get("nodes"), list) else []
        topo_edges_raw = topology_raw.get("edges") if isinstance(topology_raw.get("edges"), list) else []
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
        text_blocks = self._safe_text_list(best.get("text_blocks"), max_items=8, max_len=180)
        if df_headers and df_rows and "dataframe" not in content_modes:
            content_modes.append("dataframe")
        if (topo_nodes or topo_edges) and "topology" not in content_modes:
            content_modes.append("topology")
        if text_blocks and "text" not in content_modes:
            content_modes.append("text")
        if not content_modes:
            content_modes = ["visual"]
        return {
            "figure_id": f"docx_media_f{media_idx}",
            "source": "docx_media_vision",
            "page": 1,
            "figure_type": str(best.get("figure_type") or media_type),
            "caption": best_caption,
            "key_points": points,
            "quality": max(0.7, float(best.get("quality", 0.7) or 0.7)),
            "ref_ids": [],
            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
            "artifact_path": artifact_path,
            "content_modes": content_modes[:4],
            "dataframe": {
                "headers": df_headers,
                "rows": df_rows,
            },
            "topology": {
                "nodes": topo_nodes,
                "edges": topo_edges,
            },
            "text_blocks": text_blocks[:8],
        }
