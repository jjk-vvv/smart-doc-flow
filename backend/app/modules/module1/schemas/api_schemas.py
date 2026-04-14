from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str


class ModificationSchema(BaseModel):
    type: str
    paragraph_index: Optional[int] = None
    line_index: Optional[int] = None
    reference_text: Optional[str] = None
    run_indices: List[int] = Field(default_factory=list)
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    color: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    alignment: Optional[str] = None
    heading_level: Optional[int] = None
    line_spacing: Optional[float] = None
    space_before: Optional[float] = None
    space_after: Optional[float] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    text: Optional[str] = None
    position: Optional[str] = None


class PreviewFileSchema(BaseModel):
    name: str
    content: str
    type: str


class HealthModulesSchema(BaseModel):
    office_pdf: bool
    pypdf2: bool
    python_docx: bool
    zhipuai: bool


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    libreoffice_available: bool
    ai_available: bool
    modules: HealthModulesSchema


class StyleTransferStatus(BaseModel):
    supported: bool = False
    message: str = "样式克隆开发中，当前模块仅提供接口占位。"
