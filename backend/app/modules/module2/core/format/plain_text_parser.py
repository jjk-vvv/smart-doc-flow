from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any, Callable, Dict, List


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]

BuildHeaderMeta = Callable[[List[str]], List[Dict[str, Any]]]
DecorateRowsWithMeta = Callable[[List[Dict[str, Any]], List[str]], List[Dict[str, Any]]]
LooksLikeFigureCueText = Callable[[str], bool]


@dataclass
class PlainTextParseResult:
    text: str
    markdown: str
    bbox_map: Dict[str, List[float]]
    table_blocks: TableBlocks
    figure_blocks: FigureBlocks


_INLINE_FOOTNOTE_RE = re.compile(r"[\[【(（]\s*\d{1,3}(?:\s*[,，、]\s*\d{1,3})*\s*[\]】)）]")
_NOISE_LINE_PATTERNS = (
    re.compile(r"^(?:19|20)\d{2}$"),
    re.compile(r"^(?:19|20)\d{2}\s*[\[【(（]\s*\d{1,3}\s*[\]】)）]$"),
    re.compile(r"^[\[【(（]\s*\d{1,3}(?:\s*[,，、]\s*\d{1,3})*\s*[\]】)）]$"),
    re.compile(r"^(?:page\s*)?\d+\s*/\s*\d+$", re.IGNORECASE),
    re.compile(r"^第?\s*\d+\s*页(?:\s*/\s*共?\s*\d+\s*页)?$", re.IGNORECASE),
)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_inline_footnote_refs(text: str) -> str:
    return _INLINE_FOOTNOTE_RE.sub("", str(text or ""))


def normalize_plain_line(line: str) -> str:
    text = normalize_text(str(line or "").replace("\u3000", " "))
    if not text:
        return ""
    text = strip_inline_footnote_refs(text)
    if len(text) <= 16:
        text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=\d)\s+(?=[年月日号季度])", "", text)
    text = re.sub(r"(?<=[年月日号季度])\s+(?=\d)", "", text)
    text = re.sub(r"\s+(?=[%‰℃])", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def looks_like_noise_line(line: str) -> bool:
    text = normalize_plain_line(line)
    if not text:
        return True
    return any(pattern.fullmatch(text) for pattern in _NOISE_LINE_PATTERNS)


def looks_like_heading_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if text.startswith("#"):
        return True
    if re.match(r"^第[一二三四五六七八九十百千万\d]+[章节部分篇]", text):
        return True
    if re.match(r"^[（(][一二三四五六七八九十\d]+[)）]", text):
        return True
    if re.match(r"^[一二三四五六七八九十百千万\d]+[、.．]", text):
        return True
    if len(text) <= 36 and not re.search(r"[。！？!?；;:：]", text):
        return True
    return False


def looks_like_key_value_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    return bool(
        re.match(
            r"^[A-Za-z\u4e00-\u9fff][A-Za-z0-9_ \u4e00-\u9fff()\uFF08\uFF09\\/-]{1,40}\s*[:\uFF1A]\s*.+$",
            text,
        )
    )


def looks_like_list_item(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    return bool(re.match(r"^(?:[-*•]\s+|\d+[.)、]\s+)", text))


def split_long_text_block(block: str, max_len: int) -> List[str]:
    text = str(block or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", text) if part.strip()]
    if len(sentences) <= 1:
        return [text[idx : idx + max_len].strip() for idx in range(0, len(text), max_len) if text[idx : idx + max_len].strip()]

    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_len:
            if current:
                chunks.append(current.strip())
                current = ""
            for idx in range(0, len(sentence), max_len):
                piece = sentence[idx : idx + max_len].strip()
                if piece:
                    chunks.append(piece)
            continue
        tentative = f"{current} {sentence}".strip() if current else sentence
        if current and len(tentative) > max_len:
            chunks.append(current.strip())
            current = sentence
        else:
            current = tentative
    if current:
        chunks.append(current.strip())
    return chunks


def split_page_text(text: str, max_len: int = 700) -> List[str]:
    raw_blocks: List[str] = []
    paragraph_lines: List[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        block = " ".join(part.strip() for part in paragraph_lines if part.strip()).strip()
        paragraph_lines.clear()
        if block:
            raw_blocks.append(block)

    for raw_line in str(text or "").splitlines():
        line = normalize_plain_line(raw_line)
        if not line:
            flush_paragraph()
            continue
        if looks_like_noise_line(line):
            flush_paragraph()
            continue
        if looks_like_heading_line(line) or looks_like_key_value_line(line) or looks_like_list_item(line):
            flush_paragraph()
            raw_blocks.append(line)
            continue
        if line.count("|") >= 2 or "\t" in line:
            flush_paragraph()
            raw_blocks.append(line)
            continue
        next_block = " ".join(paragraph_lines + [line]).strip() if paragraph_lines else line
        if paragraph_lines and len(next_block) > max_len * 2:
            flush_paragraph()
        paragraph_lines.append(line)
    flush_paragraph()

    chunks: List[str] = []
    for block in raw_blocks:
        chunks.extend(split_long_text_block(block, max_len))
    return chunks


def is_markdown_table_separator(line: str) -> bool:
    tokens = [token.strip() for token in line.strip().strip("|").split("|")]
    if len(tokens) < 2:
        return False
    for token in tokens:
        core = token.replace(":", "").replace("-", "")
        if core:
            return False
        if token.count("-") < 3:
            return False
    return True


def split_markdown_row(line: str) -> List[str]:
    raw = line.strip().strip("|")
    return [cell.strip() for cell in raw.split("|")]


def parse_plain_payload(
    file_bytes: bytes,
    ext: str,
    *,
    table_max_rows: int,
    table_max_cols: int,
    nonpdf_figure_max: int,
    build_header_meta: BuildHeaderMeta,
    decorate_rows_with_meta: DecorateRowsWithMeta,
    looks_like_figure_cue_text: LooksLikeFigureCueText,
) -> PlainTextParseResult:
    decoded = ""
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
        try:
            decoded = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not decoded:
        decoded = file_bytes.decode("latin-1", errors="ignore")

    text = normalize_text(decoded)
    if not text:
        raise ValueError("Unsupported file type or empty plain text payload.")

    parts: List[str] = []
    bbox_map: Dict[str, List[float]] = {}
    table_blocks: TableBlocks = []
    figure_blocks: FigureBlocks = []

    for idx, chunk in enumerate(split_page_text(text), start=1):
        ref_id = f"text_{idx}"
        parts.append(f'<ref id="{ref_id}">{escape(chunk)}</ref>')
        bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

    normalized_ext = (ext or ".txt").lower()
    if normalized_ext in {".md", ".markdown"}:
        table_blocks.extend(
            extract_markdown_tables(
                text,
                parts,
                bbox_map,
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                build_header_meta=build_header_meta,
                decorate_rows_with_meta=decorate_rows_with_meta,
            )
        )
        figure_blocks.extend(
            extract_markdown_figures(
                text,
                parts,
                bbox_map,
                nonpdf_figure_max=nonpdf_figure_max,
                looks_like_figure_cue_text=looks_like_figure_cue_text,
            )
        )
    else:
        table_blocks.extend(
            extract_plain_text_tables(
                text,
                parts,
                bbox_map,
                table_max_rows=table_max_rows,
                table_max_cols=table_max_cols,
                build_header_meta=build_header_meta,
                decorate_rows_with_meta=decorate_rows_with_meta,
            )
        )
        figure_blocks.extend(
            extract_text_figure_cues(
                text,
                parts,
                bbox_map,
                nonpdf_figure_max=nonpdf_figure_max,
                looks_like_figure_cue_text=looks_like_figure_cue_text,
            )
        )

    return PlainTextParseResult(
        text=text,
        markdown="\n".join(parts),
        bbox_map=bbox_map,
        table_blocks=table_blocks,
        figure_blocks=figure_blocks,
    )


def extract_markdown_tables(
    text: str,
    parts: List[str],
    bbox_map: Dict[str, List[float]],
    *,
    table_max_rows: int,
    table_max_cols: int,
    build_header_meta: BuildHeaderMeta,
    decorate_rows_with_meta: DecorateRowsWithMeta,
) -> TableBlocks:
    lines = text.splitlines()
    table_blocks: TableBlocks = []
    table_idx = 1
    line_idx = 0

    while line_idx + 1 < len(lines):
        head_line = lines[line_idx].strip()
        sep_line = lines[line_idx + 1].strip()
        if head_line.count("|") < 2 or not is_markdown_table_separator(sep_line):
            line_idx += 1
            continue

        headers = split_markdown_row(head_line)
        if len(headers) < 2:
            line_idx += 1
            continue

        data_rows_raw: List[List[str]] = []
        cursor = line_idx + 2
        while cursor < len(lines):
            row_line = lines[cursor].strip()
            if row_line.count("|") < 2:
                break
            row_cells = split_markdown_row(row_line)
            if len(row_cells) < 2:
                break
            data_rows_raw.append(row_cells)
            cursor += 1

        if not data_rows_raw:
            line_idx += 1
            continue

        table_id = f"md_t{table_idx}"
        table_idx += 1
        rows_payload: List[Dict[str, Any]] = []
        for row_idx, row_cells in enumerate(data_rows_raw[:table_max_rows], start=1):
            cells_payload: List[Dict[str, Any]] = []
            for col_idx, cell_text in enumerate(row_cells[:table_max_cols], start=1):
                normalized_cell = normalize_text(cell_text)
                if not normalized_cell:
                    continue
                ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                parts.append(f'<ref id="{ref_id}">{escape(normalized_cell)}</ref>')
                bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                bbox_map[ref_id] = bbox
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": normalized_cell,
                        "ref_id": ref_id,
                        "bbox": bbox,
                    }
                )
            if cells_payload:
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})

        if rows_payload:
            header_vals = [
                (normalize_text(headers[idx]) or f"col_{idx + 1}")
                for idx in range(min(len(headers), table_max_cols))
            ]
            decorated_rows = decorate_rows_with_meta(rows_payload, header_vals)
            table_blocks.append(
                {
                    "table_id": table_id,
                    "source": "md",
                    "page": 1,
                    "headers": header_vals,
                    "header_meta": build_header_meta(header_vals),
                    "rows": decorated_rows,
                    "row_count": len(decorated_rows),
                    "col_count": max((len(row.get("cells", [])) for row in decorated_rows), default=0),
                    "quality": 0.88,
                }
            )

        line_idx = cursor

    return table_blocks


def extract_markdown_figures(
    text: str,
    parts: List[str],
    bbox_map: Dict[str, List[float]],
    *,
    nonpdf_figure_max: int,
    looks_like_figure_cue_text: LooksLikeFigureCueText,
) -> FigureBlocks:
    figures: FigureBlocks = []
    links = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)
    for idx, (alt, src) in enumerate(links[:nonpdf_figure_max], start=1):
        caption = normalize_text(alt) or f"Markdown图像 {idx}"
        src_norm = normalize_text(src)
        ref_id = f"md_fig_{idx}"
        snippet = f"{caption} ({src_norm})" if src_norm else caption
        parts.append(f'<ref id="{ref_id}">{escape(snippet)}</ref>')
        bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
        figure_type = "chart" if looks_like_figure_cue_text(f"{caption} {src_norm}") else "photo"
        figures.append(
            {
                "figure_id": f"md_f{idx}",
                "source": "md",
                "page": 1,
                "figure_type": figure_type,
                "caption": caption,
                "key_points": [src_norm] if src_norm else [],
                "quality": 0.72,
                "ref_ids": [ref_id],
                "bbox_norm": [0.0, 0.0, 1.0, 1.0],
            }
        )
    return figures


def extract_plain_text_tables(
    text: str,
    parts: List[str],
    bbox_map: Dict[str, List[float]],
    *,
    table_max_rows: int,
    table_max_cols: int,
    build_header_meta: BuildHeaderMeta,
    decorate_rows_with_meta: DecorateRowsWithMeta,
) -> TableBlocks:
    lines = [
        line
        for raw_line in text.splitlines()
        if (line := normalize_plain_line(raw_line)) and not looks_like_noise_line(line)
    ]
    groups: List[List[List[str]]] = []
    current: List[List[str]] = []

    def _split_line(raw_line: str) -> List[str]:
        if "\t" in raw_line:
            cells = [normalize_text(item) for item in raw_line.split("\t")]
        elif raw_line.count(",") >= 2:
            cells = [normalize_text(item) for item in raw_line.split(",")]
        else:
            cells = [normalize_text(item) for item in re.split(r"\s{2,}", raw_line)]
        return [cell for cell in cells if cell]

    for line in lines:
        cells = _split_line(line)
        if len(cells) >= 3:
            current.append(cells[:table_max_cols])
            continue
        if len(current) >= 3:
            groups.append(current)
        current = []
    if len(current) >= 3:
        groups.append(current)

    table_blocks: TableBlocks = []
    table_idx = 1
    for group in groups[:8]:
        header_vals = [normalize_text(item) or f"col_{idx + 1}" for idx, item in enumerate(group[0])]
        rows_payload: List[Dict[str, Any]] = []
        for row_idx, row_cells in enumerate(group[1 : table_max_rows + 1], start=1):
            cells_payload: List[Dict[str, Any]] = []
            for col_idx, cell_text in enumerate(row_cells[:table_max_cols], start=1):
                normalized_cell = normalize_text(cell_text)
                if not normalized_cell:
                    continue
                ref_id = f"txt_t{table_idx}_r{row_idx}_c{col_idx}"
                parts.append(f'<ref id="{ref_id}">{escape(normalized_cell)}</ref>')
                bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                bbox_map[ref_id] = bbox
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": normalized_cell,
                        "ref_id": ref_id,
                        "bbox": bbox,
                    }
                )
            if cells_payload:
                rows_payload.append({"row_index": row_idx, "cells": cells_payload})
        if not rows_payload:
            continue
        decorated_rows = decorate_rows_with_meta(rows_payload, header_vals)
        table_blocks.append(
            {
                "table_id": f"txt_t{table_idx}",
                "source": "txt",
                "page": 1,
                "headers": header_vals,
                "header_meta": build_header_meta(header_vals),
                "rows": decorated_rows,
                "row_count": len(decorated_rows),
                "col_count": max((len(row.get("cells", [])) for row in decorated_rows), default=0),
                "quality": 0.66,
            }
        )
        table_idx += 1

    return table_blocks


def extract_text_figure_cues(
    text: str,
    parts: List[str],
    bbox_map: Dict[str, List[float]],
    *,
    nonpdf_figure_max: int,
    looks_like_figure_cue_text: LooksLikeFigureCueText,
) -> FigureBlocks:
    lines = [
        line
        for raw_line in text.splitlines()
        if (line := normalize_plain_line(raw_line)) and not looks_like_noise_line(line)
    ]
    figure_lines = [line for line in lines if line and looks_like_figure_cue_text(line)]
    figures: FigureBlocks = []
    for idx, line in enumerate(figure_lines[:nonpdf_figure_max], start=1):
        ref_id = f"txt_fig_{idx}"
        parts.append(f'<ref id="{ref_id}">{escape(line)}</ref>')
        bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
        figures.append(
            {
                "figure_id": f"txt_f{idx}",
                "source": "txt",
                "page": 1,
                "figure_type": "chart",
                "caption": line[:120],
                "key_points": [line[:200]],
                "quality": 0.58,
                "ref_ids": [ref_id],
                "bbox_norm": [0.0, 0.0, 1.0, 1.0],
            }
        )
    return figures
