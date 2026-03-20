from __future__ import annotations

from .models import DocumentBlock, DocumentBundle, KnowledgeUnit
from .text_utils import normalize_text, stable_id


class Assistant1KnowledgeUnitExtractor:
    def extract(self, bundle: DocumentBundle) -> list[KnowledgeUnit]:
        units: list[KnowledgeUnit] = []
        units.extend(self._narrative_units(bundle))

        for block in bundle.blocks:
            if block.kind == "table":
                units.append(self._table_overview(bundle, block))
                units.extend(self._table_row_units(bundle, block))
            elif block.kind == "figure":
                units.append(self._figure_overview(bundle, block))
                units.extend(self._figure_row_units(bundle, block))
        return units

    def _narrative_units(self, bundle: DocumentBundle) -> list[KnowledgeUnit]:
        units: list[KnowledgeUnit] = []
        current_title = bundle.file_name or "Document"
        current_page = 1
        buffer: list[str] = []
        block_ids: list[str] = []
        chunk_index = 0

        def flush() -> None:
            nonlocal buffer, block_ids, chunk_index
            content = "\n\n".join(part for part in buffer if part).strip()
            if not content:
                buffer = []
                block_ids = []
                return
            chunk_index += 1
            units.append(
                KnowledgeUnit(
                    unit_id=stable_id("unit", bundle.document_id, "narrative_chunk", chunk_index, current_title),
                    document_id=bundle.document_id,
                    file_hash=bundle.file_hash,
                    unit_type="narrative_chunk",
                    title=current_title,
                    content=content,
                    page_start=current_page,
                    page_end=current_page,
                    source_block_ids=list(block_ids),
                    metadata={"chunk_index": chunk_index},
                )
            )
            buffer = []
            block_ids = []

        for block in bundle.blocks:
            if block.kind == "heading":
                flush()
                current_title = normalize_text(block.content) or current_title
                current_page = block.page_no
                buffer.append(current_title)
                block_ids.append(block.block_id)
                continue
            if block.kind != "paragraph":
                continue
            if len("\n".join(buffer)) > 1400:
                flush()
            current_page = block.page_no or current_page
            buffer.append(normalize_text(block.content))
            block_ids.append(block.block_id)

        flush()
        return units

    def _table_overview(self, bundle: DocumentBundle, block: DocumentBlock) -> KnowledgeUnit:
        headers = ", ".join(normalize_text(value) for value in block.headers if normalize_text(value))
        content_parts = [f"标题：{normalize_text(block.title)}"]
        if headers:
            content_parts.append(f"字段：{headers}")
        content_parts.append(f"行数：{len(block.rows)}")
        for bullet in block.bullets:
            content_parts.append(f"备注：{normalize_text(bullet)}")
        return KnowledgeUnit(
            unit_id=stable_id("unit", bundle.document_id, block.block_id, "table_overview"),
            document_id=bundle.document_id,
            file_hash=bundle.file_hash,
            unit_type="table_overview",
            title=normalize_text(block.title),
            content="\n".join(content_parts),
            page_start=block.page_no,
            page_end=block.page_no,
            source_block_ids=[block.block_id],
            metadata={"row_count": len(block.rows), "headers": block.headers},
        )

    def _table_row_units(self, bundle: DocumentBundle, block: DocumentBlock) -> list[KnowledgeUnit]:
        units: list[KnowledgeUnit] = []
        for row_index, row in enumerate(block.rows, start=1):
            parts = [f"表格：{normalize_text(block.title)}", f"行号：{row_index}"]
            for header, cell in zip(block.headers, row):
                parts.append(f"{normalize_text(header)}：{normalize_text(cell)}")
            units.append(
                KnowledgeUnit(
                    unit_id=stable_id("unit", bundle.document_id, block.block_id, "table_row", row_index),
                    document_id=bundle.document_id,
                    file_hash=bundle.file_hash,
                    unit_type="table_row",
                    title=f"{normalize_text(block.title)} 第{row_index}行",
                    content="\n".join(parts),
                    page_start=block.page_no,
                    page_end=block.page_no,
                    source_block_ids=[block.block_id],
                    metadata={"row_index": row_index, "headers": block.headers},
                )
            )
        return units

    def _figure_overview(self, bundle: DocumentBundle, block: DocumentBlock) -> KnowledgeUnit:
        content_parts = [f"图表标题：{normalize_text(block.title)}"]
        figure_type = normalize_text(block.metadata.get("figure_type", ""))
        if figure_type:
            content_parts.append(f"类型：{figure_type}")
        for bullet in block.bullets:
            content_parts.append(f"要点：{normalize_text(bullet)}")
        if block.headers:
            content_parts.append(f"数据字段：{', '.join(normalize_text(v) for v in block.headers if normalize_text(v))}")
        return KnowledgeUnit(
            unit_id=stable_id("unit", bundle.document_id, block.block_id, "figure_overview"),
            document_id=bundle.document_id,
            file_hash=bundle.file_hash,
            unit_type="figure_overview",
            title=normalize_text(block.title),
            content="\n".join(content_parts),
            page_start=block.page_no,
            page_end=block.page_no,
            source_block_ids=[block.block_id],
            metadata={"row_count": len(block.rows), "headers": block.headers},
        )

    def _figure_row_units(self, bundle: DocumentBundle, block: DocumentBlock) -> list[KnowledgeUnit]:
        units: list[KnowledgeUnit] = []
        for row_index, row in enumerate(block.rows, start=1):
            parts = [f"图表：{normalize_text(block.title)}", f"数据行：{row_index}"]
            for header, cell in zip(block.headers, row):
                parts.append(f"{normalize_text(header)}：{normalize_text(cell)}")
            units.append(
                KnowledgeUnit(
                    unit_id=stable_id("unit", bundle.document_id, block.block_id, "figure_dataframe_row", row_index),
                    document_id=bundle.document_id,
                    file_hash=bundle.file_hash,
                    unit_type="figure_dataframe_row",
                    title=f"{normalize_text(block.title)} 数据行{row_index}",
                    content="\n".join(parts),
                    page_start=block.page_no,
                    page_end=block.page_no,
                    source_block_ids=[block.block_id],
                    metadata={"row_index": row_index, "headers": block.headers},
                )
            )
        return units
