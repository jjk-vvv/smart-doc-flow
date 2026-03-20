from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentSourceBundle:
    file_hash: str
    file_name: str = ""
    mineru_run_key: str = ""
    mineru_run_token: str = ""
    mineru_run_dir: str = ""
    mineru_markdown_path: str = ""
    mineru_content_list_path: str = ""
    assistant_payload_path: str = ""
    images_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentItem:
    item_id: str
    item_type: str
    page_no: int
    text: str = ""
    text_level: int = 0
    bbox: list[float] = field(default_factory=list)
    img_path: str = ""
    image_caption: str = ""
    image_footnote: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualTable:
    object_id: str
    page_no: int
    title: str = ""
    caption: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    image_path: str = ""
    bbox_raw: list[float] = field(default_factory=list)
    bbox_norm: list[float] = field(default_factory=list)
    confidence: float = 0.0
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VisualFigure:
    object_id: str
    page_no: int
    figure_type: str = ""
    title: str = ""
    caption: str = ""
    insights: list[str] = field(default_factory=list)
    content_modes: list[str] = field(default_factory=list)
    dataframe_headers: list[str] = field(default_factory=list)
    dataframe_rows: list[list[str]] = field(default_factory=list)
    text_blocks: list[str] = field(default_factory=list)
    image_path: str = ""
    bbox_raw: list[float] = field(default_factory=list)
    bbox_norm: list[float] = field(default_factory=list)
    confidence: float = 0.0
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatchResult:
    content_item_id: str
    matched_kind: str = ""
    matched_object_id: str = ""
    score: float = 0.0
    status: str = "unmatched"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentBlock:
    block_id: str
    kind: str
    page_no: int
    title: str = ""
    content: str = ""
    level: int = 0
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentBundle:
    document_id: str
    file_hash: str
    file_name: str
    source_bundle: DocumentSourceBundle
    blocks: list[DocumentBlock] = field(default_factory=list)
    tables: list[VisualTable] = field(default_factory=list)
    figures: list[VisualFigure] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    build_warnings: list[str] = field(default_factory=list)
    raw_markdown_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeUnit:
    unit_id: str
    document_id: str
    file_hash: str
    unit_type: str
    title: str
    content: str
    page_start: int
    page_end: int
    source_block_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoadedSources:
    source_bundle: DocumentSourceBundle
    raw_markdown: str = ""
    content_items: list[ContentItem] = field(default_factory=list)
    tables: list[VisualTable] = field(default_factory=list)
    figures: list[VisualFigure] = field(default_factory=list)
    assistant_payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
