from __future__ import annotations

from typing import Any, TypedDict


class RuntimeSettings(TypedDict):
    api_key: str
    base_url: str
    model: str
    api_mode: str
    max_images: int
    max_image_bytes: int


class TemplateRecord(TypedDict, total=False):
    template_id: str
    template_file_id: str | None
    filename: str
    path: str
    sheet_name: str
    header_row: int
    write_row: int
    table_index: int | None
    template_type: str
    fields: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    created_at: str


class DocsetFileRecord(TypedDict):
    filename: str
    path: str
    file_id: str | None


class DocsetRecord(TypedDict):
    doc_set_id: str
    count: int
    files: list[DocsetFileRecord]
    created_at: str


class RunRecord(TypedDict, total=False):
    run_id: str
    status: str
    filled: int
    total: int
    fill_rate: float
    output_filename: str | None
    output_file_id: str | None
    error: str | None
    created_at: str
    finished_at: str
    template_id: str
    doc_set_id: str
