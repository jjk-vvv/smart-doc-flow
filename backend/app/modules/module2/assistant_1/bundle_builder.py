from __future__ import annotations

from .matcher import Assistant1Matcher
from .models import DocumentBlock, DocumentBundle, LoadedSources, VisualFigure, VisualTable
from .text_utils import normalize_text, stable_id, stable_uuid


class Assistant1BundleBuilder:
    VISUAL_CONTENT_TYPES = {"image", "equation", "formula", "table"}

    def __init__(self, matcher: Assistant1Matcher | None = None) -> None:
        self.matcher = matcher or Assistant1Matcher()

    def build(self, loaded: LoadedSources) -> DocumentBundle:
        match_map, unmatched_content, unmatched_objects = self.matcher.match(
            loaded.content_items,
            loaded.tables,
            loaded.figures,
        )
        table_map = {table.object_id: table for table in loaded.tables}
        figure_map = {figure.object_id: figure for figure in loaded.figures}

        blocks: list[DocumentBlock] = []
        warnings = list(loaded.warnings)
        for item in loaded.content_items:
            if item.item_type == "text":
                if not item.text:
                    continue
                kind = "heading" if item.text_level > 0 else "paragraph"
                blocks.append(
                    DocumentBlock(
                        block_id=stable_id("block", item.item_id, kind),
                        kind=kind,
                        page_no=item.page_no,
                        title=item.text if kind == "heading" else "",
                        content=item.text,
                        level=item.text_level if kind == "heading" else 0,
                        metadata={"content_item_id": item.item_id, "bbox": item.bbox},
                    )
                )
                continue

            if item.item_type not in self.VISUAL_CONTENT_TYPES:
                continue

            match = match_map.get(item.item_id)
            if match and match.matched_kind == "table":
                table = table_map.get(match.matched_object_id)
                if table:
                    blocks.append(self._table_block(item.item_id, item.page_no, table, match.status, match.score))
                    continue
            if match and match.matched_kind == "figure":
                figure = figure_map.get(match.matched_object_id)
                if figure:
                    blocks.append(self._figure_block(item.item_id, item.page_no, figure, match.status, match.score))
                    continue

            _fallback_caption = item.image_caption or item.image_footnote or ""
            blocks.append(
                DocumentBlock(
                    block_id=stable_id("block", item.item_id, "image_unresolved"),
                    kind="image_unresolved",
                    page_no=item.page_no,
                    title=item.image_caption,
                    content=(
                        f"{_fallback_caption} (page {item.page_no})".strip()
                        if _fallback_caption
                        else f"Unresolved visual on page {item.page_no}"
                    ),
                    metadata={
                        "content_item_id": item.item_id,
                        "content_item_type": item.item_type,
                        "img_path": item.img_path,
                        "image_footnote": item.image_footnote,
                        "bbox": item.bbox,
                    },
                )
            )

        if unmatched_content:
            warnings.append(f"unmatched content image count={len(unmatched_content)}")
        if unmatched_objects:
            warnings.append(f"unmatched assistant payload object count={len(unmatched_objects)}")

        stats = {
            "content_item_count": len(loaded.content_items),
            "block_count": len(blocks),
            "table_count": len(loaded.tables),
            "figure_count": len(loaded.figures),
            "unmatched_content_image_count": len(unmatched_content),
            "unmatched_payload_object_count": len(unmatched_objects),
        }
        return DocumentBundle(
            document_id=stable_uuid("document", loaded.source_bundle.file_hash),
            file_hash=loaded.source_bundle.file_hash,
            file_name=loaded.source_bundle.file_name,
            source_bundle=loaded.source_bundle,
            blocks=blocks,
            tables=loaded.tables,
            figures=loaded.figures,
            stats=stats,
            build_warnings=warnings,
            raw_markdown_source=loaded.raw_markdown,
        )

    def _table_block(
        self,
        content_item_id: str,
        page_no: int,
        table: VisualTable,
        match_status: str,
        match_score: float,
    ) -> DocumentBlock:
        title = table.caption or table.title
        if not title and table.headers:
            title = "表格：" + " / ".join(header for header in table.headers[:3] if header)
        if not title:
            title = f"Table on page {page_no}"
        return DocumentBlock(
            block_id=stable_id("block", content_item_id, table.object_id),
            kind="table",
            page_no=page_no or table.page_no,
            title=title,
            content=title,
            headers=list(table.headers),
            rows=[list(row) for row in table.rows],
            bullets=[note for note in table.notes if note],
            metadata={
                "content_item_id": content_item_id,
                "table_id": table.object_id,
                "match_status": match_status,
                "match_score": round(match_score, 4),
                "confidence": table.confidence,
                "image_path": table.image_path,
                "bbox_raw": table.bbox_raw,
                "bbox_norm": table.bbox_norm,
            },
        )

    def _figure_block(
        self,
        content_item_id: str,
        page_no: int,
        figure: VisualFigure,
        match_status: str,
        match_score: float,
    ) -> DocumentBlock:
        title = figure.caption or figure.title
        if not title and figure.figure_type == "formula" and figure.text_blocks:
            title = figure.text_blocks[0][:80]
        if not title:
            title = f"Figure on page {page_no}"
        bullets = list(figure.insights)
        if not bullets and figure.text_blocks:
            bullets = list(figure.text_blocks[:6])
        return DocumentBlock(
            block_id=stable_id("block", content_item_id, figure.object_id),
            kind="figure",
            page_no=page_no or figure.page_no,
            title=title,
            content=normalize_text(title),
            headers=list(figure.dataframe_headers),
            rows=[list(row) for row in figure.dataframe_rows],
            bullets=bullets,
            metadata={
                "content_item_id": content_item_id,
                "figure_id": figure.object_id,
                "match_status": match_status,
                "match_score": round(match_score, 4),
                "figure_type": figure.figure_type,
                "content_modes": figure.content_modes,
                "text_blocks": figure.text_blocks,
                "confidence": figure.confidence,
                "image_path": figure.image_path,
                "bbox_raw": figure.bbox_raw,
                "bbox_norm": figure.bbox_norm,
            },
        )
