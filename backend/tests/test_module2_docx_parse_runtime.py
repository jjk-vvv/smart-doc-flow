from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


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


docx_runtime_module = _load_module(
    ["module2", "app", "core", "format", "docx_document_runtime.py"],
    "_smart_doc_flow_module2_docx_document_runtime_for_parse",
)
rows_runtime_module = _load_module(
    ["module2", "app", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_table_rows_runtime_for_docx",
)
text_runtime_module = _load_module(
    ["module2", "app", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_text_runtime_for_docx",
)

DocxParseRuntime = docx_runtime_module.DocxParseRuntime
NonPdfTableRowsRuntime = rows_runtime_module.NonPdfTableRowsRuntime
NonPdfTextRuntime = text_runtime_module.NonPdfTextRuntime


class _FakeParagraph:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeCell:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeRow:
    def __init__(self, *cells: str) -> None:
        self.cells = [_FakeCell(text) for text in cells]


class _FakeTable:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self.rows = rows


class _FakeDoc:
    def __init__(self, paragraphs: list[_FakeParagraph], tables: list[_FakeTable]) -> None:
        self.paragraphs = paragraphs
        self.tables = tables


def _build_runtime() -> DocxParseRuntime:
    normalize = lambda text: " ".join(str(text or "").split())
    rows_runtime = NonPdfTableRowsRuntime(normalize_text=normalize)
    text_runtime = NonPdfTextRuntime(normalize_text=normalize)

    def build_table_block(*, table_id, source, page, rows_payload, extra_fields=None):
        if not rows_payload:
            return None
        return {
            "table_id": table_id,
            "source": source,
            "page": page,
            "row_count": len(rows_payload),
            **dict(extra_fields or {}),
        }

    return DocxParseRuntime(
        table_max_rows=10,
        table_max_cols=5,
        normalize_text=normalize,
        append_numbered_text_ref=text_runtime.append_numbered_text_ref,
        build_rows_payload=rows_runtime.build_rows_payload,
        build_table_block=build_table_block,
    )


def test_docx_parse_runtime_consumes_document_text_and_tables() -> None:
    runtime = _build_runtime()
    doc = _FakeDoc(
        paragraphs=[
            _FakeParagraph(" 第\u4e00段 "),
            _FakeParagraph(""),
            _FakeParagraph("第二段"),
        ],
        tables=[_FakeTable([_FakeRow("表头", "值"), _FakeRow("城市", "120")])],
    )
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    table_blocks, ref_idx = runtime.consume_document(
        doc=doc,
        parts=parts,
        bbox_map=bbox_map,
        start_ref_idx=1,
    )

    assert ref_idx == 3
    assert '<ref id="docx_1">第\u4e00段</ref>' in parts
    assert '<ref id="docx_2">第二段</ref>' in parts
    assert any("docx_t1_r2_c2" in part for part in parts)
    assert len(table_blocks) == 1
    assert table_blocks[0]["table_id"] == "docx_t1"


def test_docx_parse_runtime_consumes_relaxed_xml_root() -> None:
    runtime = _build_runtime()
    root = ET.fromstring(
        """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>放宽</w:t></w:r><w:r><w:t>解析</w:t></w:r></w:p>
            <w:p><w:r><w:t>第二段</w:t></w:r></w:p>
            <w:tbl>
              <w:tr>
                <w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>数值</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>产量</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>42</w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
          </w:body>
        </w:document>
        """
    )
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    table_blocks, ref_idx = runtime.consume_relaxed_root(
        root=root,
        ns=ns,
        parts=parts,
        bbox_map=bbox_map,
        start_ref_idx=1,
    )

    assert ref_idx == 7
    assert '<ref id="docx_relaxed_1">放宽解析</ref>' in parts
    assert '<ref id="docx_relaxed_2">第二段</ref>' in parts
    assert '<ref id="docx_relaxed_3">项目</ref>' in parts
    assert any("docx_relaxed_t1_r2_c2" in part for part in parts)
    assert len(table_blocks) == 1
    assert table_blocks[0]["source"] == "docx_relaxed"
