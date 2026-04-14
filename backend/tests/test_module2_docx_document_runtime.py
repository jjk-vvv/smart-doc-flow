from __future__ import annotations

import importlib.util
import io
import sys
import types
import zipfile
from pathlib import Path

import pytest


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


docx_document_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "docx_document_runtime.py"],
    "_smart_doc_flow_module2_docx_document_runtime",
)

DocxDocumentRuntime = docx_document_runtime_module.DocxDocumentRuntime


def _build_docx_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()


def test_docx_document_runtime_parses_native_docx_and_merges_enrichment(monkeypatch) -> None:
    fake_doc = object()
    monkeypatch.setitem(sys.modules, "docx", types.SimpleNamespace(Document=lambda stream: fake_doc))

    def _consume_document(*, doc, parts, bbox_map, start_ref_idx):
        assert doc is fake_doc
        parts.append('<ref id="docx_1">alpha</ref>')
        bbox_map["docx_1"] = [1.0, 0.0, 0.0, 1.0, 1.0]
        return ([{"table_id": "docx_t1"}], 2)

    runtime = DocxDocumentRuntime(
        nonpdf_figure_max=8,
        consume_document=_consume_document,
        extract_docx_chart_and_media=lambda **kwargs: (
            [{"figure_id": "docx_media_f1"}],
            [{"table_id": "docx_media_t1"}],
            {"docx_media_used": 1},
            3,
        ),
        merge_figure_blocks=lambda left, right: left + right,
        consume_relaxed_root=lambda **kwargs: ([], 1),
        append_text_ref=lambda **kwargs: True,
    )

    result = runtime.parse_docx(b"docx")

    assert result["markdown"] == '<ref id="docx_1">alpha</ref>'
    assert result["bbox_map"]["docx_1"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert [table["table_id"] for table in result["table_blocks"]] == ["docx_t1", "docx_media_t1"]
    assert result["figure_blocks"] == [{"figure_id": "docx_media_f1"}]
    assert result["stats"] == {"docx_media_used": 1}


def test_docx_document_runtime_falls_back_to_relaxed_mode_when_docx_document_open_fails(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "docx",
        types.SimpleNamespace(Document=lambda stream: (_ for _ in ()).throw(RuntimeError("broken archive"))),
    )

    runtime = DocxDocumentRuntime(
        nonpdf_figure_max=8,
        consume_document=lambda **kwargs: ([], 1),
        extract_docx_chart_and_media=lambda **kwargs: ([], [], {}, 1),
        merge_figure_blocks=lambda left, right: left + right,
        consume_relaxed_root=lambda **kwargs: (
            [{"table_id": "docx_relaxed_t1"}],
            2,
        )
        if kwargs["parts"].append('<ref id="docx_relaxed_1">fallback</ref>') is None
        else ([], 1),
        append_text_ref=lambda **kwargs: True,
    )

    file_bytes = _build_docx_zip(
        {
            "word/document.xml": """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body><w:p><w:r><w:t>fallback</w:t></w:r></w:p></w:body>
            </w:document>
            """,
        }
    )
    result = runtime.parse_docx(file_bytes)

    assert result["markdown"] == '<ref id="docx_relaxed_1">fallback</ref>'
    assert result["table_blocks"] == [{"table_id": "docx_relaxed_t1"}]
    assert result["stats"] == {"docx_relaxed_mode": True}


def test_docx_document_runtime_relaxed_mode_appends_placeholder_when_no_text() -> None:
    state: dict[str, object] = {}

    def _append_text_ref(*, ref_id, text, parts, bbox_map):
        parts.append(f'<ref id="{ref_id}">{text}</ref>')
        bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
        state["called"] = True
        return True

    runtime = DocxDocumentRuntime(
        nonpdf_figure_max=8,
        consume_document=lambda **kwargs: ([], 1),
        extract_docx_chart_and_media=lambda **kwargs: ([], [], {}, 1),
        merge_figure_blocks=lambda left, right: left + right,
        consume_relaxed_root=lambda **kwargs: ([], 1),
        append_text_ref=_append_text_ref,
    )

    file_bytes = _build_docx_zip(
        {
            "word/document.xml": """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body></w:body>
            </w:document>
            """,
        }
    )
    result = runtime.parse_docx_relaxed(file_bytes)

    assert state["called"] is True
    assert "docx_relaxed_empty" in result["bbox_map"]
    assert "文档未识别到可提取正文" in result["markdown"]
    assert result["stats"] == {"docx_relaxed_mode": True}


def test_docx_document_runtime_raises_when_native_docx_has_no_extractable_text(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "docx", types.SimpleNamespace(Document=lambda stream: object()))

    runtime = DocxDocumentRuntime(
        nonpdf_figure_max=8,
        consume_document=lambda **kwargs: ([], 1),
        extract_docx_chart_and_media=lambda **kwargs: ([], [], {}, 1),
        merge_figure_blocks=lambda left, right: left + right,
        consume_relaxed_root=lambda **kwargs: ([], 1),
        append_text_ref=lambda **kwargs: True,
    )

    with pytest.raises(ValueError, match="DOCX contains no extractable text."):
        runtime.parse_docx(b"docx")
