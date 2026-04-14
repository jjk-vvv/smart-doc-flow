from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ContentItem, DocumentSourceBundle, LoadedSources, VisualFigure, VisualTable
from .text_utils import caption_text, normalize_text, repair_text, stable_id


class Assistant1SourceLoader:
    def load(self, source_bundle: DocumentSourceBundle) -> LoadedSources:
        warnings = list(source_bundle.warnings)
        raw_markdown = ""
        content_items: list[ContentItem] = []
        tables: list[VisualTable] = []
        figures: list[VisualFigure] = []
        assistant_payload: dict[str, Any] = {}

        markdown_path = Path(source_bundle.mineru_markdown_path) if source_bundle.mineru_markdown_path else None
        if markdown_path and markdown_path.exists():
            raw_markdown = markdown_path.read_text(encoding="utf-8", errors="ignore")
        else:
            warnings.append("MinerU markdown artifact is missing or unreadable")

        content_list_path = Path(source_bundle.mineru_content_list_path) if source_bundle.mineru_content_list_path else None
        if content_list_path and content_list_path.exists():
            raw_content_list = self._read_json(content_list_path)
            if isinstance(raw_content_list, list):
                content_items = self._parse_content_items(raw_content_list)
            else:
                warnings.append("content_list artifact is not a list")
        else:
            warnings.append("MinerU content_list artifact is missing or unreadable")

        assistant_payload_path = Path(source_bundle.assistant_payload_path) if source_bundle.assistant_payload_path else None
        if assistant_payload_path and assistant_payload_path.exists():
            assistant_payload = self._read_json(assistant_payload_path)
            tables = self._parse_tables(assistant_payload.get("tables", []))
            figures = self._parse_figures(assistant_payload.get("figures", []))
        else:
            warnings.append("assistant payload artifact is missing or unreadable")

        if not content_items and raw_markdown:
            content_items = self._build_markdown_fallback_items(raw_markdown)
            warnings.append("content_list unavailable; fell back to markdown-only content items")

        return LoadedSources(
            source_bundle=source_bundle,
            raw_markdown=raw_markdown,
            content_items=content_items,
            tables=tables,
            figures=figures,
            assistant_payload=assistant_payload,
            warnings=warnings,
        )

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def _parse_content_items(self, payload: list[dict[str, Any]]) -> list[ContentItem]:
        items: list[ContentItem] = []
        for idx, item in enumerate(payload, start=1):
            item_type = str(item.get("type", "") or "").strip().lower()
            if not item_type or item_type == "discarded":
                continue
            page_no = int(item.get("page_idx", 0) or 0) + 1
            text = repair_text(item.get("text", "") or "")
            items.append(
                ContentItem(
                    item_id=stable_id("content", page_no, idx, item_type, text, item.get("img_path", "")),
                    item_type=item_type,
                    page_no=page_no,
                    text=text,
                    text_level=int(item.get("text_level", 0) or 0),
                    bbox=[float(v) for v in item.get("bbox", []) if isinstance(v, (int, float))],
                    img_path=str(item.get("img_path", "") or ""),
                    image_caption=caption_text(item.get("image_caption", [])),
                    image_footnote=caption_text(item.get("image_footnote", [])),
                    metadata={
                        k: v
                        for k, v in item.items()
                        if k not in {"type", "text", "text_level", "bbox", "page_idx", "img_path", "image_caption", "image_footnote"}
                    },
                )
            )
        return items

    def _parse_tables(self, payload: Any) -> list[VisualTable]:
        items: list[VisualTable] = []
        for table in payload or []:
            headers = [normalize_text(value) for value in table.get("headers", []) if normalize_text(value)]
            rows: list[list[str]] = []
            for row in table.get("rows", []) or []:
                cells = row.get("cells") if isinstance(row, dict) else row
                parsed_row: list[str] = []
                if isinstance(cells, list):
                    for cell in cells:
                        if isinstance(cell, dict):
                            parsed_row.append(normalize_text(cell.get("text", "")))
                        else:
                            parsed_row.append(normalize_text(cell))
                if parsed_row:
                    rows.append(parsed_row)
            items.append(
                VisualTable(
                    object_id=str(table.get("table_id", "") or stable_id("table", table.get("page", ""), table.get("image_path", ""))),
                    page_no=int(table.get("page", 0) or 0),
                    title=normalize_text(table.get("title", "")),
                    caption=normalize_text(table.get("caption", "")),
                    headers=headers,
                    rows=rows,
                    notes=[normalize_text(note) for note in table.get("notes", []) if normalize_text(note)],
                    image_path=str(table.get("image_path", "") or ""),
                    bbox_raw=[float(v) for v in table.get("bbox_raw", []) if isinstance(v, (int, float))],
                    bbox_norm=[float(v) for v in table.get("bbox_norm", []) if isinstance(v, (int, float))],
                    confidence=float(table.get("quality", table.get("confidence", 0.0)) or 0.0),
                    raw_payload=table,
                )
            )
        return items

    def _parse_figures(self, payload: Any) -> list[VisualFigure]:
        items: list[VisualFigure] = []
        for figure in payload or []:
            dataframe = figure.get("dataframe", {}) if isinstance(figure.get("dataframe"), dict) else {}
            headers = [normalize_text(value) for value in dataframe.get("headers", []) if normalize_text(value)]
            rows: list[list[str]] = []
            for row in dataframe.get("rows", []) or []:
                if isinstance(row, list):
                    rows.append([normalize_text(value) for value in row])
            items.append(
                VisualFigure(
                    object_id=str(figure.get("figure_id", "") or stable_id("figure", figure.get("page", ""), figure.get("image_path", ""))),
                    page_no=int(figure.get("page", 0) or 0),
                    figure_type=normalize_text(figure.get("figure_type", figure.get("type", ""))),
                    title=normalize_text(figure.get("title", "")),
                    caption=normalize_text(figure.get("caption", "")),
                    insights=[normalize_text(value) for value in figure.get("insights", []) if normalize_text(value)],
                    content_modes=[normalize_text(value) for value in figure.get("content_modes", []) if normalize_text(value)],
                    dataframe_headers=headers,
                    dataframe_rows=rows,
                    text_blocks=[normalize_text(value) for value in figure.get("text_blocks", []) if normalize_text(value)],
                    image_path=str(figure.get("image_path", "") or ""),
                    bbox_raw=[float(v) for v in figure.get("bbox_raw", []) if isinstance(v, (int, float))],
                    bbox_norm=[float(v) for v in figure.get("bbox_norm", []) if isinstance(v, (int, float))],
                    confidence=float(figure.get("quality", figure.get("confidence", 0.0)) or 0.0),
                    raw_payload=figure,
                )
            )
        return items

    def _build_markdown_fallback_items(self, raw_markdown: str) -> list[ContentItem]:
        items: list[ContentItem] = []
        for idx, line in enumerate(raw_markdown.splitlines(), start=1):
            text = repair_text(line)
            if not text:
                continue
            text_level = 0
            plain_text = text
            if text.startswith("#"):
                stripped = text.lstrip("#").strip()
                text_level = max(1, len(text) - len(text.lstrip("#")))
                plain_text = stripped
            items.append(
                ContentItem(
                    item_id=stable_id("mdcontent", idx, plain_text),
                    item_type="text",
                    page_no=1,
                    text=plain_text,
                    text_level=text_level,
                )
            )
        return items
