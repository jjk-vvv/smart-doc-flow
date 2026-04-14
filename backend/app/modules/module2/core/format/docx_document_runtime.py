from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
RowsPayload = List[Dict[str, Any]]
ChartTables = List[Dict[str, Any]]

ConsumeDocument = Callable[..., Tuple[TableBlocks, int]]
ExtractDocxChartAndMedia = Callable[..., Tuple[FigureBlocks, TableBlocks, Dict[str, Any], int]]
MergeFigureBlocks = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]
ConsumeRelaxedRoot = Callable[..., Tuple[TableBlocks, int]]
AppendTextRef = Callable[..., bool]
AppendNumberedTextRef = Callable[..., int]
BuildRowsPayload = Callable[..., RowsPayload]
BuildTableBlock = Callable[..., Optional[Dict[str, Any]]]
NormalizeText = Callable[[str], str]
ExtractDocxChartXmlTables = Callable[[bytes], Tuple[ChartTables, Dict[str, Any]]]
FindMatchingPdfFigureIndex = Callable[..., int | None]
TableBlockToDataframe = Callable[[Dict[str, Any]], Tuple[List[str], List[List[str]]]]
SafeTextList = Callable[..., List[str]]
ParsePdf = Callable[..., Tuple[str, Dict[str, List[float]], TableBlocks]]
ConvertWordBytesToPdf = Callable[..., Tuple[bytes, Dict[str, Any]]]


class DocxParseRuntime:
    """Consume DOCX document structures into parser-compatible refs and table blocks."""

    def __init__(
        self,
        *,
        table_max_rows: int,
        table_max_cols: int,
        normalize_text: NormalizeText,
        append_numbered_text_ref: AppendNumberedTextRef,
        build_rows_payload: BuildRowsPayload,
        build_table_block: BuildTableBlock,
    ) -> None:
        self.table_max_rows = max(1, int(table_max_rows or 1))
        self.table_max_cols = max(1, int(table_max_cols or 1))
        self._normalize_text = normalize_text
        self._append_numbered_text_ref = append_numbered_text_ref
        self._build_rows_payload = build_rows_payload
        self._build_table_block = build_table_block

    def consume_document(
        self,
        *,
        doc: Any,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        start_ref_idx: int = 1,
    ) -> Tuple[TableBlocks, int]:
        ref_idx = max(1, int(start_ref_idx or 1))
        table_blocks: TableBlocks = []

        for para in getattr(doc, "paragraphs", []) or []:
            ref_idx = self._append_numbered_text_ref(
                ref_prefix="docx",
                ref_idx=ref_idx,
                text=getattr(para, "text", "") or "",
                parts=parts,
                bbox_map=bbox_map,
            )

        for table_idx, table in enumerate(getattr(doc, "tables", []) or [], start=1):
            table_id = f"docx_t{table_idx}"
            rows_payload = self._build_rows_payload(
                table_id=table_id,
                rows=getattr(table, "rows", []) or [],
                get_cells=lambda row: getattr(row, "cells", []) or [],
                get_cell_text=lambda cell: getattr(cell, "text", "") or "",
                max_rows=self.table_max_rows,
                max_cols=self.table_max_cols,
                parts=parts,
                bbox_map=bbox_map,
            )
            table_block = self._build_table_block(
                table_id=table_id,
                source="docx",
                page=1,
                rows_payload=rows_payload,
            )
            if table_block:
                table_blocks.append(table_block)

        return table_blocks, ref_idx

    def consume_relaxed_root(
        self,
        *,
        root: Any,
        ns: Dict[str, str],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        start_ref_idx: int = 1,
    ) -> Tuple[TableBlocks, int]:
        ref_idx = max(1, int(start_ref_idx or 1))
        table_blocks: TableBlocks = []

        for para in root.findall(".//w:p", ns):
            ref_idx = self._append_numbered_text_ref(
                ref_prefix="docx_relaxed",
                ref_idx=ref_idx,
                text=self._joined_relaxed_text(para.findall(".//w:t", ns)),
                parts=parts,
                bbox_map=bbox_map,
            )

        for table_idx, table in enumerate(root.findall(".//w:tbl", ns), start=1):
            table_id = f"docx_relaxed_t{table_idx}"
            rows_payload = self._build_rows_payload(
                table_id=table_id,
                rows=table.findall("./w:tr", ns),
                get_cells=lambda row: row.findall("./w:tc", ns),
                get_cell_text=lambda cell: self._joined_relaxed_text(cell.findall(".//w:t", ns)),
                max_rows=self.table_max_rows,
                max_cols=self.table_max_cols,
                parts=parts,
                bbox_map=bbox_map,
            )
            table_block = self._build_table_block(
                table_id=table_id,
                source="docx_relaxed",
                page=1,
                rows_payload=rows_payload,
            )
            if table_block:
                table_blocks.append(table_block)

        return table_blocks, ref_idx

    def _joined_relaxed_text(self, nodes: List[Any]) -> str:
        tokens = [self._normalize_text(str(getattr(node, "text", "") or "")) for node in nodes]
        return self._normalize_text("".join(token for token in tokens if token))


class DocxChartMergeRuntime:
    """Merge DOCX chart-xml tables into recovered PDF figures without changing parser semantics."""

    def __init__(
        self,
        *,
        extract_docx_chart_xml_tables: ExtractDocxChartXmlTables,
        normalize_text: NormalizeText,
        find_matching_pdf_figure_index: FindMatchingPdfFigureIndex,
        table_block_to_dataframe: TableBlockToDataframe,
        safe_text_list: SafeTextList,
    ) -> None:
        self._extract_docx_chart_xml_tables = extract_docx_chart_xml_tables
        self._normalize_text = normalize_text
        self._find_matching_pdf_figure_index = find_matching_pdf_figure_index
        self._table_block_to_dataframe = table_block_to_dataframe
        self._safe_text_list = safe_text_list

    def merge_docx_chart_xml_into_pdf_figures(
        self,
        *,
        file_bytes: bytes,
        figure_blocks: FigureBlocks,
    ) -> Dict[str, Any]:
        chart_tables, chart_stats = self._extract_docx_chart_xml_tables(file_bytes)
        stats_patch = dict(chart_stats or {})
        if not chart_tables or not figure_blocks:
            stats_patch["docx_chart_xml_merged"] = int(stats_patch.get("docx_chart_xml_merged", 0) or 0)
            return {
                "figure_blocks": [dict(item) for item in (figure_blocks or [])],
                "stats_patch": stats_patch,
            }

        merged_figures: FigureBlocks = [dict(item) for item in figure_blocks]
        merged_count = 0
        unmatched_count = 0
        for table in chart_tables:
            chart_title = self._normalize_text(str(table.get("chart_title", "") or ""))
            figure_idx = self._find_matching_pdf_figure_index(
                chart_title=chart_title,
                figure_blocks=merged_figures,
            )
            if figure_idx is None:
                unmatched_count += 1
                continue

            headers, rows = self._table_block_to_dataframe(table)
            if not headers or not rows:
                unmatched_count += 1
                continue

            figure = dict(merged_figures[figure_idx])
            dataframe = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
            existing_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
            if existing_rows:
                continue

            figure["dataframe"] = {"headers": headers, "rows": rows}
            figure["dataframe_source"] = "docx_chart_xml_merge"
            modes = [
                self._normalize_text(str(item or "")).lower()
                for item in (figure.get("content_modes") if isinstance(figure.get("content_modes"), list) else [])
            ]
            modes = [item for item in modes if item in {"dataframe", "topology", "text", "visual"}]
            if "visual" not in modes:
                modes.append("visual")
            if "dataframe" not in modes:
                modes.insert(0, "dataframe")
            figure["content_modes"] = modes[:4]
            figure["quality"] = max(0.72, float(figure.get("quality", 0.0) or 0.0))
            insights = self._safe_text_list(figure.get("insights"), max_items=8, max_len=180)
            insights.append(f"dataframe: {len(rows)}x{max(len(row) for row in rows)}")
            figure["insights"] = insights[:8]
            merged_figures[figure_idx] = figure
            merged_count += 1

        stats_patch["docx_chart_xml_merged"] = merged_count
        stats_patch["docx_chart_xml_unmatched"] = unmatched_count
        return {
            "figure_blocks": merged_figures,
            "stats_patch": stats_patch,
        }


class DocxViaPdfRuntime:
    """Coordinate DOCX conversion and handoff into the PDF parser."""

    def __init__(
        self,
        *,
        word_pdf_timeout_sec: int,
        word_pdf_parse_use_source_signals: bool,
        word_pdf_docx_chart_xml_merge_enable: bool,
        convert_word_bytes_to_pdf: ConvertWordBytesToPdf,
        parse_pdf: ParsePdf,
    ) -> None:
        self.word_pdf_timeout_sec = max(1, int(word_pdf_timeout_sec or 1))
        self.word_pdf_parse_use_source_signals = bool(word_pdf_parse_use_source_signals)
        self.word_pdf_docx_chart_xml_merge_enable = bool(word_pdf_docx_chart_xml_merge_enable)
        self._convert_word_bytes_to_pdf = convert_word_bytes_to_pdf
        self._parse_pdf = parse_pdf

    def parse_docx_via_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
    ) -> Dict[str, Any]:
        pdf_bytes, convert_meta = self._convert_word_bytes_to_pdf(
            file_name=file_name,
            file_bytes=file_bytes,
            timeout_sec=self.word_pdf_timeout_sec,
        )
        pdf_name = f"{Path(file_name).stem}.pdf"
        word_source_cache_identity = hashlib.sha256(bytes(file_bytes)).hexdigest() if file_bytes else ""
        parse_source_file_name = file_name if self.word_pdf_parse_use_source_signals else None
        parse_source_file_bytes = file_bytes if self.word_pdf_parse_use_source_signals else None
        markdown, bbox_map, table_blocks = self._parse_pdf(
            pdf_name,
            pdf_bytes,
            "VisualTrack",
            source_file_name=parse_source_file_name,
            source_file_bytes=parse_source_file_bytes,
            source_cache_identity=word_source_cache_identity,
        )
        stats_patch = {
            "word_via_pdf": True,
            "office_pdf_converted": True,
            "office_pdf_converter": str(convert_meta.get("converter", "")),
            "office_pdf_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
            "office_pdf_cache_hit": bool(convert_meta.get("cache_hit")),
            "office_pdf_cache_waited_ms": int(convert_meta.get("cache_waited_ms", 0) or 0),
            "office_pdf_artifact_path": str(convert_meta.get("artifact_path", "") or ""),
            "office_pdf_artifact_url": str(convert_meta.get("artifact_url", "") or ""),
            "office_pdf_parse_input_name": pdf_name,
            "office_pdf_bytes": len(pdf_bytes),
            "word_pdf_parse_use_source_signals": bool(self.word_pdf_parse_use_source_signals),
            "word_pdf_parse_source_signals_applied": bool(parse_source_file_name),
            "word_pdf_docx_chart_xml_merge_enabled": bool(self.word_pdf_docx_chart_xml_merge_enable),
            "docx_source_file_name": str(file_name or ""),
        }
        if word_source_cache_identity:
            stats_patch["source_cache_identity_applied"] = True
            stats_patch["source_cache_identity_file_name"] = str(file_name or "")
        return {
            "markdown": markdown,
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "stats_patch": stats_patch,
        }


class DocxDocumentRuntime:
    """Coordinate DOCX native parsing and relaxed fallback without changing parser-facing behavior."""

    _RELAXED_EMPTY_PLACEHOLDER = (
        "\u6587\u6863\u672a\u8bc6\u522b\u5230\u53ef\u63d0\u53d6\u6b63\u6587\uff0c"
        "\u53ef\u80fd\u4e3a\u56fe\u7247\u7248\u6216\u4ec5\u5305\u542b\u5bf9\u8c61\u5143\u7d20\u3002"
    )

    def __init__(
        self,
        *,
        nonpdf_figure_max: int,
        consume_document: ConsumeDocument,
        extract_docx_chart_and_media: ExtractDocxChartAndMedia,
        merge_figure_blocks: MergeFigureBlocks,
        consume_relaxed_root: ConsumeRelaxedRoot,
        append_text_ref: AppendTextRef,
    ) -> None:
        self.nonpdf_figure_max = max(0, int(nonpdf_figure_max or 0))
        self._consume_document = consume_document
        self._extract_docx_chart_and_media = extract_docx_chart_and_media
        self._merge_figure_blocks = merge_figure_blocks
        self._consume_relaxed_root = consume_relaxed_root
        self._append_text_ref = append_text_ref

    def parse_docx(self, file_bytes: bytes) -> Dict[str, Any]:
        from docx import Document

        try:
            doc = Document(io.BytesIO(file_bytes))
        except Exception:
            return self.parse_docx_relaxed(file_bytes)

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        figure_blocks: FigureBlocks = []
        table_blocks, ref_idx = self._consume_document(
            doc=doc,
            parts=parts,
            bbox_map=bbox_map,
            start_ref_idx=1,
        )

        extra_figures, extra_tables, docx_stats, ref_idx = self._extract_docx_chart_and_media(
            file_bytes=file_bytes,
            parts=parts,
            bbox_map=bbox_map,
            start_ref_idx=ref_idx,
        )
        if extra_tables:
            table_blocks.extend(extra_tables)
        if extra_figures:
            figure_blocks.extend(extra_figures[: self.nonpdf_figure_max])

        if not parts:
            raise ValueError("DOCX contains no extractable text.")

        return {
            "markdown": "\n".join(parts),
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "figure_blocks": self._merge_figure_blocks([], figure_blocks),
            "stats": dict(docx_stats or {}),
        }

    def parse_docx_relaxed(self, file_bytes: bytes) -> Dict[str, Any]:
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                raw_xml = zf.read("word/document.xml")
        except Exception as exc:
            raise ValueError(f"DOCX fallback parsing failed: {exc}") from exc

        try:
            root = ET.fromstring(raw_xml)
        except Exception as exc:
            raise ValueError(f"DOCX XML decode failed: {exc}") from exc

        table_blocks, _ = self._consume_relaxed_root(
            root=root,
            ns=ns,
            parts=parts,
            bbox_map=bbox_map,
            start_ref_idx=1,
        )

        if not parts:
            self._append_text_ref(
                ref_id="docx_relaxed_empty",
                text=self._RELAXED_EMPTY_PLACEHOLDER,
                parts=parts,
                bbox_map=bbox_map,
            )

        return {
            "markdown": "\n".join(parts),
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "figure_blocks": [],
            "stats": {"docx_relaxed_mode": True},
        }
