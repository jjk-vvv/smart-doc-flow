from __future__ import annotations

import importlib.util
import io
import sys
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


xlsx_parse_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "xlsx_runtime.py"],
    "_smart_doc_flow_module2_xlsx_parse_runtime",
)

XlsxParseRuntime = xlsx_parse_runtime_module.XlsxParseRuntime


class _FakeWorkbook:
    def __init__(self, *, worksheets=None, sheetnames=None):
        self.worksheets = list(worksheets or [])
        self.sheetnames = list(sheetnames or [])


def _build_runtime(state: dict[str, object]) -> XlsxParseRuntime:
    def _consume_openpyxl_workbook(*, workbook, source_tag, emitted_cells, parts, bbox_map):
        state["openpyxl_tags"] = list(state.get("openpyxl_tags", [])) + [source_tag]
        if source_tag == "xlsx" and getattr(workbook, "worksheets", None):
            parts.append('<ref id="xlsx_t1_r1_c1">A</ref>')
            bbox_map["xlsx_t1_r1_c1"] = [1.0, 0.0, 0.0, 1.0, 1.0]
            return ([{"table_id": "xlsx_t1", "source": "xlsx"}], emitted_cells + 1)
        if source_tag == "xlsx_formula" and getattr(workbook, "worksheets", None):
            parts.append('<ref id="xlsx_formula_t1_r1_c1">=SUM(A:A)</ref>')
            bbox_map["xlsx_formula_t1_r1_c1"] = [1.0, 0.0, 0.0, 1.0, 1.0]
            return ([{"table_id": "xlsx_formula_t1", "source": "xlsx_formula"}], emitted_cells + 1)
        return ([], emitted_cells)

    def _consume_zip_workbook(*, file_bytes, source_tag, emitted_cells, parts, bbox_map):
        if state.get("zip_emits"):
            parts.append('<ref id="xlsx_t1_r1_c1">zip</ref>')
            bbox_map["xlsx_t1_r1_c1"] = [1.0, 0.0, 0.0, 1.0, 1.0]
            return ([{"table_id": "xlsx_t1", "source": source_tag}], emitted_cells + 1, True)
        return ([], emitted_cells, False)

    def _append_xlsx_sheet_placeholders(*, sheet_names, sheet_limit, parts, bbox_map):
        emitted = 0
        for idx, sheet_name in enumerate(sheet_names[:sheet_limit], start=1):
            parts.append(f'<ref id="xlsx_sheet_{idx}">工作表：{sheet_name}</ref>')
            bbox_map[f"xlsx_sheet_{idx}"] = [float(idx), 0.0, 0.0, 1.0, 1.0]
            emitted += 1
        return emitted

    def _append_text_ref(*, ref_id, text, parts, bbox_map):
        parts.append(f'<ref id="{ref_id}">{text}</ref>')
        bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
        return True

    return XlsxParseRuntime(
        sheet_limit=3,
        consume_openpyxl_workbook=_consume_openpyxl_workbook,
        consume_zip_workbook=_consume_zip_workbook,
        append_xlsx_sheet_placeholders=_append_xlsx_sheet_placeholders,
        append_text_ref=_append_text_ref,
    )


def test_xlsx_parse_runtime_prefers_openpyxl_data_workbook() -> None:
    state: dict[str, object] = {}
    runtime = _build_runtime(state)

    def _load_workbook(stream: io.BytesIO, *, data_only: bool, read_only: bool):
        assert read_only is True
        return _FakeWorkbook(worksheets=[object()], sheetnames=["Sheet1"])

    markdown, bbox_map, table_blocks, used_zip = runtime.parse_xlsx(
        file_bytes=b"fake",
        load_workbook=_load_workbook,
    )

    assert used_zip is False
    assert "xlsx_t1_r1_c1" in markdown
    assert bbox_map["xlsx_t1_r1_c1"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert table_blocks == [{"table_id": "xlsx_t1", "source": "xlsx"}]
    assert state["openpyxl_tags"] == ["xlsx"]


def test_xlsx_parse_runtime_uses_zip_fallback_when_openpyxl_yields_nothing() -> None:
    state: dict[str, object] = {"zip_emits": True}
    runtime = _build_runtime(state)

    def _load_workbook(stream: io.BytesIO, *, data_only: bool, read_only: bool):
        return _FakeWorkbook(worksheets=[], sheetnames=["Sheet1"])

    markdown, bbox_map, table_blocks, used_zip = runtime.parse_xlsx(
        file_bytes=b"fake",
        load_workbook=_load_workbook,
    )

    assert used_zip is True
    assert "xlsx_t1_r1_c1" in markdown
    assert table_blocks == [{"table_id": "xlsx_t1", "source": "xlsx"}]


def test_xlsx_parse_runtime_emits_sheet_placeholders_when_cells_missing() -> None:
    state: dict[str, object] = {}
    runtime = _build_runtime(state)

    def _load_workbook(stream: io.BytesIO, *, data_only: bool, read_only: bool):
        return _FakeWorkbook(worksheets=[], sheetnames=["预算表", "图表页"])

    markdown, bbox_map, table_blocks, used_zip = runtime.parse_xlsx(
        file_bytes=b"fake",
        load_workbook=_load_workbook,
    )

    assert used_zip is False
    assert '<ref id="xlsx_sheet_1">工作表：预算表</ref>' in markdown
    assert '<ref id="xlsx_sheet_2">工作表：图表页</ref>' in markdown
    assert bbox_map["xlsx_sheet_2"] == [2.0, 0.0, 0.0, 1.0, 1.0]
    assert table_blocks == []


def test_xlsx_parse_runtime_emits_empty_workbook_placeholder_when_sheet_names_missing() -> None:
    state: dict[str, object] = {}
    runtime = _build_runtime(state)

    def _load_workbook(stream: io.BytesIO, *, data_only: bool, read_only: bool):
        raise RuntimeError("broken workbook")

    markdown, bbox_map, table_blocks, used_zip = runtime.parse_xlsx(
        file_bytes=b"fake",
        load_workbook=_load_workbook,
    )

    assert used_zip is False
    assert '<ref id="xlsx_sheet_1">工作簿中未检测到可提取工作表，已按空结构文件处理。</ref>' in markdown
    assert bbox_map["xlsx_sheet_1"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert table_blocks == []
