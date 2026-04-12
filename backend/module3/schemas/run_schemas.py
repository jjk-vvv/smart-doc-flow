from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WebRunRequest(BaseModel):
    template_id: str
    doc_set_id: str
    prompt: str | None = None
    api_mode: str | None = None


class UpdateExcelSheet(BaseModel):
    name: str
    rows: list[list[str | int | float | None]]


class UpdateExcelRequest(BaseModel):
    sheets: list[UpdateExcelSheet]


class ExcelParseRequest(BaseModel):
    run_id: str


class UpdateWordSection(BaseModel):
    id: str
    name: str
    type: str
    order: int
    content: str | None = None
    rows: list[list[str | int | float | None]] | None = None


class UpdateWordRequest(BaseModel):
    sections: list[UpdateWordSection]


class WordParseRequest(BaseModel):
    run_id: str


class WordParagraphDiff(BaseModel):
    paragraph_index: int
    text: str | None = None


class WordCellDiff(BaseModel):
    row: int
    col: int
    value: str | int | float | None = None


class WordSectionDiff(BaseModel):
    section_id: str
    type: str
    paragraphs: list[WordParagraphDiff] | None = None
    cells: list[WordCellDiff] | None = None


class WordStructureAction(BaseModel):
    section_id: str
    action_type: Literal["insert_row", "delete_row", "insert_col", "delete_col"]
    index: int
    count: int = 1


class WordApplyDiffRequest(BaseModel):
    run_id: str
    sections: list[WordSectionDiff] = Field(default_factory=list)
    actions: list[WordStructureAction] = Field(default_factory=list)


__all__ = [
    "WebRunRequest",
    "UpdateExcelRequest",
    "UpdateExcelSheet",
    "ExcelParseRequest",
    "UpdateWordRequest",
    "UpdateWordSection",
    "WordApplyDiffRequest",
    "WordCellDiff",
    "WordParagraphDiff",
    "WordParseRequest",
    "WordSectionDiff",
    "WordStructureAction",
]
