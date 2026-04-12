from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path


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


nonpdf_rows_module = _load_module(
    ["module2", "app", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_table_rows_runtime_for_xlsx_table",
)
xlsx_runtime_module = _load_module(
    ["module2", "app", "core", "format", "xlsx_runtime.py"],
    "_smart_doc_flow_module2_xlsx_runtime_for_table",
)
NonPdfTableRowsRuntime = nonpdf_rows_module.NonPdfTableRowsRuntime
XlsxRuntime = xlsx_runtime_module.XlsxRuntime
XlsxTableRuntime = xlsx_runtime_module.XlsxTableRuntime


class _FakeSheet:
    def __init__(self, title: str, rows: list[tuple[object, ...]]) -> None:
        self.title = title
        self._rows = rows
        self.max_row = len(rows)
        self.max_column = max((len(row) for row in rows), default=0)

    def iter_rows(self, *, values_only: bool = False):
        assert values_only is True
        for row in self._rows:
            yield row


class _FakeWorkbook:
    def __init__(self, worksheets: list[_FakeSheet]) -> None:
        self.worksheets = worksheets


def _build_runtime() -> XlsxTableRuntime:
    rows_runtime = NonPdfTableRowsRuntime(normalize_text=lambda text: " ".join(str(text or "").split()))
    xlsx_runtime = XlsxRuntime(normalize_text=lambda text: " ".join(str(text or "").split()), sheet_limit=4)

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

    return XlsxTableRuntime(
        sheet_limit=4,
        table_max_rows=20,
        table_max_cols=5,
        xlsx_cell_cap=12,
        xlsx_runtime=xlsx_runtime,
        build_indexed_rows_payload=rows_runtime.build_indexed_rows_payload,
        build_table_block=build_table_block,
    )


def _build_zip(files: dict[str, str]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return stream.getvalue()


def test_xlsx_table_runtime_consumes_openpyxl_workbook() -> None:
    runtime = _build_runtime()
    workbook = _FakeWorkbook([_FakeSheet("Sheet1", [("地区", "数值"), ("城市", 120), ("农村", 80)])])
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    tables, emitted = runtime.consume_openpyxl_workbook(
        workbook=workbook,
        source_tag="xlsx",
        emitted_cells=0,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert emitted == 6
    assert len(tables) == 1
    assert tables[0]["table_id"] == "xlsx_t1"
    assert tables[0]["sheet_name"] == "Sheet1"
    assert "xlsx_t1_r1_c1" in "".join(parts)
    assert "xlsx_t1_r3_c2" in bbox_map


def test_xlsx_table_runtime_consumes_zip_workbook() -> None:
    runtime = _build_runtime()
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}
    file_bytes = _build_zip(
        {
            "xl/_rels/workbook.xml.rels": """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
                </Relationships>
            """,
            "xl/workbook.xml": """
                <workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <sheets>
                    <sheet name="Sheet1" r:id="rId1"/>
                  </sheets>
                </workbook>
            """,
            "xl/sharedStrings.xml": """
                <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <si><t>地区</t></si>
                  <si><t>城市</t></si>
                </sst>
            """,
            "xl/worksheets/sheet1.xml": """
                <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <dimension ref="A1:B2"/>
                  <sheetData>
                    <row r="1">
                      <c r="A1" t="s"><v>0</v></c>
                      <c r="B1"><v>120</v></c>
                    </row>
                    <row r="2">
                      <c r="A2" t="s"><v>1</v></c>
                      <c r="B2"><v>80</v></c>
                    </row>
                  </sheetData>
                </worksheet>
            """,
        }
    )

    tables, emitted, used_zip = runtime.consume_zip_workbook(
        file_bytes=file_bytes,
        source_tag="xlsx",
        emitted_cells=0,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert used_zip is True
    assert emitted == 4
    assert len(tables) == 1
    assert tables[0]["sheet_index"] == 1
    assert tables[0]["sheet_name"] == "Sheet1"
    assert "xlsx_t1_r2_c2" in bbox_map
