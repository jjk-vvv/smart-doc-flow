from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from ..core.database import Base


class TemplateTable(Base):
    __tablename__ = "module3_templates"

    template_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default=text("'default'"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    header_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    write_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fields_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tables_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DocsetTable(Base):
    __tablename__ = "module3_docsets"

    doc_set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default=text("'default'"),
        index=True,
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    files: Mapped[list["DocsetFileTable"]] = relationship(
        back_populates="docset",
        cascade="all, delete-orphan",
        order_by="DocsetFileTable.id",
    )


class DocsetFileTable(Base):
    __tablename__ = "module3_docset_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_set_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("module3_docsets.doc_set_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)

    docset: Mapped["DocsetTable"] = relationship(back_populates="files")


class RunTable(Base):
    __tablename__ = "module3_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="default",
        server_default=text("'default'"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    filled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fill_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    doc_set_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list["RunLogTable"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="RunLogTable.id",
    )


class RunLogTable(Base):
    __tablename__ = "module3_run_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("module3_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    run: Mapped["RunTable"] = relationship(back_populates="logs")


__all__ = [
    "DocsetFileTable",
    "DocsetTable",
    "RunLogTable",
    "RunTable",
    "TemplateTable",
]
