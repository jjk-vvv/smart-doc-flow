from __future__ import annotations

from .models import DocumentBlock, DocumentBundle
from .text_utils import escape_pipe, normalize_text


class Assistant1MarkdownRenderer:
    def render(self, bundle: DocumentBundle) -> tuple[str, str, list[dict[str, object]]]:
        raw_lines: list[str] = []
        clean_lines: list[str] = []
        merged_index: list[dict[str, object]] = []

        for block in bundle.blocks:
            raw_lines.extend(self._render_block(block, debug=True))
            clean_lines.extend(self._render_block(block, debug=False))
            merged_index.append(
                {
                    "block_id": block.block_id,
                    "kind": block.kind,
                    "page_no": block.page_no,
                    "title": block.title,
                    "metadata": block.metadata,
                }
            )

        raw_markdown = "\n".join(raw_lines).strip() + "\n"
        clean_candidate = "\n".join(clean_lines).strip() + "\n"
        return raw_markdown, clean_candidate, merged_index

    def _render_block(self, block: DocumentBlock, debug: bool) -> list[str]:
        lines: list[str] = []
        if debug:
            lines.append(f"<!-- block:{block.block_id} kind:{block.kind} page:{block.page_no} -->")

        if block.kind == "heading":
            level = min(max(block.level or 1, 1), 6)
            lines.append(f"{'#' * level} {normalize_text(block.content)}")
            lines.append("")
            return lines

        if block.kind == "paragraph":
            lines.append(normalize_text(block.content))
            lines.append("")
            return lines

        if block.kind == "table":
            lines.append(f"**表格**：{normalize_text(block.title)}")
            lines.append("")
            lines.extend(self._render_markdown_table(block.headers, block.rows))
            if block.bullets:
                lines.append("")
                lines.append("备注：")
                for bullet in block.bullets:
                    lines.append(f"- {normalize_text(bullet)}")
            lines.append("")
            return lines

        if block.kind == "figure":
            lines.append(f"**图像/图表**：{normalize_text(block.title)}")
            if block.bullets:
                lines.append("")
                for bullet in block.bullets:
                    lines.append(f"- {normalize_text(bullet)}")
            if block.headers and block.rows:
                lines.append("")
                lines.append("图中数据：")
                lines.extend(self._render_markdown_table(block.headers, block.rows))
            lines.append("")
            return lines

        if block.kind == "image_unresolved":
            lines.append(f"**图像占位**：{normalize_text(block.title or block.content)}")
            if debug and block.metadata.get("img_path"):
                lines.append(f"原始图片：{block.metadata['img_path']}")
            lines.append("")
            return lines

        if block.content:
            lines.append(normalize_text(block.content))
            lines.append("")
        return lines

    def _render_markdown_table(self, headers: list[str], rows: list[list[str]]) -> list[str]:
        lines: list[str] = []
        if headers:
            header_row = "| " + " | ".join(escape_pipe(value) for value in headers) + " |"
            separator = "| " + " | ".join("---" for _ in headers) + " |"
            lines.extend([header_row, separator])
            for row in rows:
                padded = list(row) + [""] * max(0, len(headers) - len(row))
                lines.append("| " + " | ".join(escape_pipe(value) for value in padded[: len(headers)]) + " |")
            return lines

        for row in rows:
            if row:
                lines.append("- " + " | ".join(normalize_text(value) for value in row))
        return lines
