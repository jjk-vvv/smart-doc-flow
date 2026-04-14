from __future__ import annotations

import importlib.util
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


text_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "format", "nonpdf_content_runtime.py"],
    "_smart_doc_flow_module2_nonpdf_text_runtime",
)

NonPdfTextRuntime = text_runtime_module.NonPdfTextRuntime


def test_nonpdf_text_runtime_appends_text_ref_with_escape_and_default_bbox() -> None:
    runtime = NonPdfTextRuntime(normalize_text=lambda text: " ".join(str(text or "").split()))
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    emitted = runtime.append_text_ref(
        ref_id="docx_1",
        text=" A < B ",
        parts=parts,
        bbox_map=bbox_map,
    )

    assert emitted is True
    assert parts == ['<ref id="docx_1">A &lt; B</ref>']
    assert bbox_map["docx_1"] == [1.0, 0.0, 0.0, 1.0, 1.0]


def test_nonpdf_text_runtime_numbered_ref_skips_blank_text() -> None:
    runtime = NonPdfTextRuntime(normalize_text=lambda text: str(text or "").strip())
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    ref_idx = runtime.append_numbered_text_ref(
        ref_prefix="docx_relaxed",
        ref_idx=3,
        text="   ",
        parts=parts,
        bbox_map=bbox_map,
    )
    next_ref_idx = runtime.append_numbered_text_ref(
        ref_prefix="docx_relaxed",
        ref_idx=ref_idx,
        text="正文",
        parts=parts,
        bbox_map=bbox_map,
        bbox=[2.0, 0.1, 0.2, 0.3, 0.4],
    )

    assert ref_idx == 3
    assert next_ref_idx == 4
    assert parts == ['<ref id="docx_relaxed_3">正文</ref>']
    assert bbox_map["docx_relaxed_3"] == [2.0, 0.1, 0.2, 0.3, 0.4]


def test_nonpdf_text_runtime_appends_xlsx_sheet_placeholders_with_limit() -> None:
    runtime = NonPdfTextRuntime(normalize_text=lambda text: " ".join(str(text or "").split()))
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}

    emitted = runtime.append_xlsx_sheet_placeholders(
        sheet_names=[" Sheet A ", "", "Sheet C"],
        sheet_limit=2,
        parts=parts,
        bbox_map=bbox_map,
    )

    assert emitted == 2
    assert '<ref id="xlsx_sheet_1">工作表：Sheet A（未检测到可提取单元格，可能为图表或公式驱动文件）</ref>' in parts
    assert '<ref id="xlsx_sheet_2">工作表：Sheet2（未检测到可提取单元格，可能为图表或公式驱动文件）</ref>' in parts
    assert "xlsx_sheet_3" not in bbox_map
    assert bbox_map["xlsx_sheet_2"] == [2.0, 0.0, 0.0, 1.0, 1.0]
