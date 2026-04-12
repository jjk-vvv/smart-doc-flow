from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
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


xlsx_runtime_module = _load_module(
    ["module2", "app", "core", "format", "xlsx_runtime.py"],
    "_smart_doc_flow_module2_xlsx_runtime",
)

XlsxRuntime = xlsx_runtime_module.XlsxRuntime


def _build_zip(files: dict[str, str]) -> zipfile.ZipFile:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    stream.seek(0)
    return zipfile.ZipFile(stream)


def test_xlsx_runtime_ref_helpers_parse_dimension_hints() -> None:
    runtime = XlsxRuntime(normalize_text=lambda text: " ".join(str(text or "").split()), sheet_limit=4)

    assert runtime.col_to_index("A") == 1
    assert runtime.col_to_index("AB") == 28
    assert runtime.ref_to_row_col("C12") == (12, 3)
    assert runtime.dimension_hints("A1:D8") == (8, 4)
    assert runtime.dimension_hints("") == (1, 1)


def test_xlsx_runtime_reads_sheet_entries_and_shared_strings() -> None:
    runtime = XlsxRuntime(normalize_text=lambda text: " ".join(str(text or "").split()), sheet_limit=4)
    with _build_zip(
        {
            "xl/_rels/workbook.xml.rels": """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
                </Relationships>
            """,
            "xl/workbook.xml": """
                <workbook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <sheets>
                    <sheet name=" Sheet 1 " r:id="rId1"/>
                  </sheets>
                </workbook>
            """,
            "xl/sharedStrings.xml": """
                <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                  <si><t> hello </t></si>
                </sst>
            """,
        }
    ) as zf:
        assert runtime.sheet_entries_from_zip(zf) == [(1, "Sheet 1", "xl/worksheets/sheet1.xml")]
        assert runtime.shared_strings_from_zip(zf) == ["hello"]


def test_xlsx_runtime_extracts_cell_text_from_xml_variants() -> None:
    runtime = XlsxRuntime(normalize_text=lambda text: str(text or "").strip(), sheet_limit=4)

    shared_cell = ET.fromstring('<c t="s"><v>0</v></c>')
    inline_cell = ET.fromstring('<c t="inlineStr"><is><t>inline</t></is></c>')
    bool_cell = ET.fromstring('<c t="b"><v>1</v></c>')
    formula_cell = ET.fromstring('<c><f>SUM(A1:A2)</f></c>')

    assert runtime.cell_text_from_xml(shared_cell, ["shared"]) == "shared"
    assert runtime.cell_text_from_xml(inline_cell, []) == "inline"
    assert runtime.cell_text_from_xml(bool_cell, []) == "TRUE"
    assert runtime.cell_text_from_xml(formula_cell, []) == "=SUM(A1:A2)"
