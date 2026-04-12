from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path
from typing import Any


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


docx_enrichment_module = _load_module(
    ["module2", "app", "core", "format", "docx_enrichment.py"],
    "_smart_doc_flow_module2_docx_enrichment",
)

DocxEnrichmentRuntime = docx_enrichment_module.DocxEnrichmentRuntime


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values[:max_items]:
        text = _normalize_text(str(item or ""))
        if text:
            out.append(text[:max_len])
    return out


def _looks_like_figure_cue_text(text: str) -> bool:
    probe = _normalize_text(text).lower()
    return any(token in probe for token in ("chart", "figure", "graph", "plot", "图"))


def _normalize_dataframe_headers(headers: Any, *, max_len: int = 120) -> list[str]:
    if not isinstance(headers, list):
        return []
    return [_normalize_text(str(item or ""))[:max_len] for item in headers if _normalize_text(str(item or ""))]


def _normalize_dataframe_matrix(rows: Any, *, max_cell_len: int = 160) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    out: list[list[str]] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        out.append([_normalize_text(str(cell or ""))[:max_cell_len] for cell in row])
    return out


def _decorate_rows_with_meta(rows_payload: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for row in rows_payload:
        copied_row = dict(row)
        copied_cells: list[dict[str, Any]] = []
        for cell in row.get("cells", []):
            copied_cell = dict(cell)
            col_index = int(copied_cell.get("col_index", 0) or 0)
            copied_cell["header"] = headers[col_index - 1] if 1 <= col_index <= len(headers) else ""
            copied_cells.append(copied_cell)
        copied_row["cells"] = copied_cells
        decorated.append(copied_row)
    return decorated


def _build_header_meta(headers: list[str]) -> list[dict[str, Any]]:
    return [{"name": _normalize_text(header), "col_index": idx + 1} for idx, header in enumerate(headers)]


def _build_docx_zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            zf.writestr(name, payload)
    return buffer.getvalue()


def _build_runtime(
    tmp_path: Path,
    *,
    state: dict[str, Any] | None = None,
    parse_image=None,
    **overrides,
):
    runtime_state = state if state is not None else {"figures": []}

    def _parse_image(*, file_name: str, file_bytes: bytes, enable_gemini_enhance: bool = True):
        if parse_image is None:
            return "", {}, []
        return parse_image(
            file_name=file_name,
            file_bytes=file_bytes,
            enable_gemini_enhance=enable_gemini_enhance,
        )

    def _get_last_figure_blocks():
        return [dict(item) for item in runtime_state.get("figures", [])]

    def _set_last_figure_blocks(figure_blocks):
        runtime_state["figures"] = [dict(item) for item in (figure_blocks or [])]

    config = {
        "artifact_root_dir": tmp_path,
        "image_extensions": {".png", ".jpg", ".jpeg"},
        "docx_chart_xml_enable": True,
        "docx_media_probe_enable": True,
        "docx_media_max_assets": 8,
        "docx_media_vision_enable": True,
        "docx_media_nested_gemini_enhance_enable": True,
        "docx_media_max_assets_unbounded": False,
        "docx_media_vision_max_assets": 4,
        "docx_media_vision_max_assets_unbounded": False,
        "docx_media_vision_max_bytes": 1024 * 1024,
        "docx_media_vision_chart_only": False,
        "docx_media_vision_allow_noncue": True,
        "nonpdf_figure_max": 8,
        "normalize_text": _normalize_text,
        "safe_text_list": _safe_text_list,
        "looks_like_figure_cue_text": _looks_like_figure_cue_text,
        "normalize_dataframe_headers": _normalize_dataframe_headers,
        "normalize_dataframe_matrix": _normalize_dataframe_matrix,
        "decorate_rows_with_meta": _decorate_rows_with_meta,
        "build_header_meta": _build_header_meta,
        "parse_image": _parse_image,
        "get_last_figure_blocks": _get_last_figure_blocks,
        "set_last_figure_blocks": _set_last_figure_blocks,
    }
    config.update(overrides)
    return DocxEnrichmentRuntime(**config), runtime_state


CHART_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <c:chart>
    <c:title>
      <c:tx>
        <c:rich>
          <a:p><a:r><a:t>季度营收</a:t></a:r></a:p>
        </c:rich>
      </c:tx>
    </c:title>
    <c:plotArea>
      <c:barChart>
        <c:ser>
          <c:tx><c:v>华东</c:v></c:tx>
          <c:cat>
            <c:strRef>
              <c:strCache>
                <c:pt idx="0"><c:v>Q1</c:v></c:pt>
                <c:pt idx="1"><c:v>Q2</c:v></c:pt>
              </c:strCache>
            </c:strRef>
          </c:cat>
          <c:val>
            <c:numRef>
              <c:numCache>
                <c:pt idx="0"><c:v>10</c:v></c:pt>
                <c:pt idx="1"><c:v>20</c:v></c:pt>
              </c:numCache>
            </c:numRef>
          </c:val>
        </c:ser>
      </c:barChart>
    </c:plotArea>
  </c:chart>
</c:chartSpace>
"""


def test_docx_enrichment_runtime_extracts_chart_xml_table_from_docx_zip(tmp_path: Path) -> None:
    runtime, _state = _build_runtime(tmp_path, docx_media_probe_enable=False)
    file_bytes = _build_docx_zip({"word/charts/chart1.xml": CHART_XML})

    tables, stats = runtime.extract_docx_chart_xml_tables(file_bytes)

    assert stats["docx_chart_xml_seen"] == 1
    assert stats["docx_chart_xml_parsed"] == 1
    assert len(tables) == 1
    assert tables[0]["chart_title"] == "季度营收"
    assert tables[0]["headers"] == ["序列", "类别", "数值"]
    assert tables[0]["rows"][0]["cells"][0]["text"] == "华东"
    assert tables[0]["rows"][0]["cells"][1]["text"] == "Q1"
    assert tables[0]["rows"][1]["cells"][2]["text"] == "20"


def test_docx_enrichment_runtime_uses_media_vision_and_restores_parser_figure_state(tmp_path: Path) -> None:
    initial_state = {"figures": [{"figure_id": "seed", "caption": "before"}]}

    def _fake_parse_image(*, file_name: str, file_bytes: bytes, enable_gemini_enhance: bool = True):
        initial_state["figures"] = [
            {
                "figure_id": "nested",
                "figure_type": "chart",
                "caption": "收入趋势图",
                "key_points": ["Q1=10", "Q2=20"],
                "quality": 0.92,
                "content_modes": ["visual", "dataframe"],
                "dataframe": {
                    "headers": ["季度", "营收"],
                    "rows": [["Q1", "10"], ["Q2", "20"]],
                },
                "topology": {
                    "nodes": [{"id": "n1", "label": "开始", "type": "step"}],
                    "edges": [],
                },
                "text_blocks": ["图表显示季度营收变化"],
            }
        ]
        return "", {}, [{"table_id": "nested_table", "headers": ["A"], "rows": [], "row_count": 0, "col_count": 1}]

    runtime, state = _build_runtime(tmp_path, state=initial_state, parse_image=_fake_parse_image)
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}
    file_bytes = _build_docx_zip({"word/media/chart_revenue.png": b"fake-image-bytes"})

    figures, tables, stats, ref_idx = runtime.extract_docx_chart_and_media(
        file_bytes=file_bytes,
        parts=parts,
        bbox_map=bbox_map,
        start_ref_idx=10,
    )

    assert ref_idx == 11
    assert stats["docx_media_parsed"] == 1
    assert stats["docx_media_used"] == 1
    assert figures[0]["source"] == "docx_media_vision"
    assert figures[0]["caption"] == "收入趋势图"
    assert "dataframe" in figures[0]["content_modes"]
    assert figures[0]["ref_ids"] == ["docx_media_1_vision"]
    assert Path(figures[0]["artifact_path"]).exists()
    assert tables[0]["source"] == "docx_media_vision"
    assert tables[0]["table_id"] == "docx_media_t1_1"
    assert parts and "收入趋势图" in parts[0]
    assert bbox_map["docx_media_1_vision"] == [1.0, 0.0, 0.0, 1.0, 1.0]
    assert state["figures"] == [{"figure_id": "seed", "caption": "before"}]


def test_docx_enrichment_runtime_falls_back_to_probe_figure_when_vision_disabled(tmp_path: Path) -> None:
    runtime, _state = _build_runtime(
        tmp_path,
        docx_chart_xml_enable=False,
        docx_media_vision_enable=False,
    )
    parts: list[str] = []
    bbox_map: dict[str, list[float]] = {}
    file_bytes = _build_docx_zip({"word/media/photo.png": b"plain-photo"})

    figures, tables, stats, ref_idx = runtime.extract_docx_chart_and_media(
        file_bytes=file_bytes,
        parts=parts,
        bbox_map=bbox_map,
        start_ref_idx=1,
    )

    assert ref_idx == 2
    assert not tables
    assert stats["docx_media_fallback_count"] == 1
    assert stats["docx_media_used"] == 1
    assert figures[0]["source"] == "docx_media"
    assert figures[0]["figure_type"] == "photo"
    assert "DOCX内嵌图像 photo.png" in figures[0]["caption"]
    assert parts and "大小" in parts[0]


def test_docx_enrichment_runtime_skips_duplicate_media_assets(tmp_path: Path) -> None:
    runtime, _state = _build_runtime(
        tmp_path,
        docx_chart_xml_enable=False,
        docx_media_vision_enable=False,
        docx_media_max_assets=10,
    )
    duplicate_bytes = b"same-image"
    file_bytes = _build_docx_zip(
        {
            "word/media/image1.png": duplicate_bytes,
            "word/media/image2.png": duplicate_bytes,
        }
    )

    figures, tables, stats, ref_idx = runtime.extract_docx_chart_and_media(
        file_bytes=file_bytes,
        parts=[],
        bbox_map={},
        start_ref_idx=3,
    )

    assert ref_idx == 4
    assert not tables
    assert len(figures) == 1
    assert stats["docx_media_seen"] == 2
    assert stats["docx_media_skipped_duplicate"] == 1
    assert stats["docx_media_used"] == 1
