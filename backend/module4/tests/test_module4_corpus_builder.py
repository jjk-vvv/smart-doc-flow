from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.ingestion.text_corpus import (  # noqa: E402
    _collect_payload_text_fragments,
    _compose_document_text,
    _normalize_fragment_text,
)


def test_normalize_fragment_text_filters_display_shell_lines() -> None:
    text = """
    表格标题 | 计量单位 | 2024年   page_4_table_2
    图像 3：趋势图
    2024年药品流通市场规模同比增长7.2%
    """

    normalized = _normalize_fragment_text(text, keep_structured=False)

    assert "page_4_table_2" not in normalized
    assert "表格标题" not in normalized
    assert "2024年药品流通市场规模同比增长7.2%" in normalized


def test_collect_payload_text_fragments_prefers_semantic_table_and_figure_text() -> None:
    payload = {
        "tables": [
            {
                "title": "表 1 药品流通统计",
                "summary": "表格显示药品销售额保持稳定增长。",
                "headers": ["年份", "销售额", "同比增速"],
                "rows": [
                    {
                        "cells": [
                            {"text": "2024年", "header": "年份"},
                            {"text": "120亿元", "header": "销售额"},
                            {"text": "7.2%", "header": "同比增速"},
                        ]
                    }
                ],
            }
        ],
        "figures": [
            {
                "title": "图 2 市场趋势",
                "summary": "图表显示 2021 至 2024 年持续增长。",
                "key_points": ["东部地区增速最快。"],
            }
        ],
    }

    fragments = _collect_payload_text_fragments(payload)
    texts = [text for text, _bucket in fragments]

    assert any("药品销售额保持稳定增长" in text for text in texts)
    assert any("销售额为120亿元" in text and "同比增速为7.2%" in text for text in texts)
    assert any("2021 至 2024 年持续增长" in text for text in texts)
    assert not any("表格标题 |" in text for text in texts)


def test_compose_document_text_keeps_semantic_content_and_avoids_trace_shells() -> None:
    doc = {
        "file_name": "demo.docx",
        "text_corpus": "这是正文摘要。该报告指出产业规模持续增长。",
        "source_texts": [
            {"kind": "semantic_summary", "text": "图表解析表明，2024年同比增长7.2%。"},
            {"kind": "trace", "text": "page_2_table_1"},
        ],
        "trace_hits": [
            {
                "object_type": "table",
                "object_id": "page_2_table_1",
                "snippet": "表格显示 2024 年销售额为 120 亿元。",
                "locator": {"title": "表格标题 | 计量单位 | 2024年"},
            }
        ],
    }

    corpus = _compose_document_text(doc)

    assert "文档标题：demo.docx" in corpus
    assert "这是正文摘要" in corpus
    assert "2024年同比增长7.2%" in corpus
    assert "2024 年销售额为 120 亿元" in corpus
    assert "page_2_table_1" not in corpus
    assert "表格标题 | 计量单位 | 2024年" not in corpus


def test_compose_document_text_skips_mojibake_markdown_but_keeps_clean_payload(tmp_path: Path, monkeypatch) -> None:
    artifact_root = tmp_path / "runtime-data" / "module2" / "artifacts"
    markdown_dir = artifact_root / "assistant_1_source" / "demo"
    payload_dir = artifact_root / "assistant_payload" / "demo"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    payload_dir.mkdir(parents=True, exist_ok=True)

    markdown_rel = "assistant_1_source/demo/source.md"
    payload_rel = "assistant_payload/demo/payload.json"

    (markdown_dir / "source.md").write_text(
        "<ref id=\"xlsx_t1_r1_c1\">鍩庡競</ref>\n<ref id=\"xlsx_t1_r1_c2\">鐩戞祴鏃堕棿</ref>\n",
        encoding="utf-8",
    )
    (payload_dir / "payload.json").write_text(
        json.dumps(
            {
                "tables": [
                    {
                        "summary": "山东省环境空气质量监测数据显示，重点站点 AQI 保持在较低水平。",
                        "headers": ["城市", "AQI"],
                        "rows": [
                            {
                                "cells": [
                                    {"header": "城市", "text": "济南市"},
                                    {"header": "AQI", "text": "52"},
                                ]
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("SMART_DOC_FLOW_RUNTIME_ROOT", str(tmp_path))
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(artifact_root))

    doc = {
        "file_name": "demo.xlsx",
        "diagnostics": {
            "assistant1_source_markdown_artifact_path": markdown_rel,
            "assistant_payload_artifact_path": payload_rel,
        },
    }

    corpus = _compose_document_text(doc)

    assert "重点站点 AQI 保持在较低水平" in corpus
    assert "城市为济南市" in corpus
    assert "鍩庡競" not in corpus
    assert "鐩戞祴鏃堕棿" not in corpus


def test_compose_document_text_ingests_xlsx_workbook_manifest_and_rows(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path
    artifact_root = runtime_root / "runtime-data" / "module2" / "artifacts"
    sheet_dir = artifact_root / "xlsx_workbook" / "abc123" / "sheets"
    sheet_dir.mkdir(parents=True, exist_ok=True)

    rows_rel = "xlsx_workbook/abc123/sheets/demo_rows.json"
    manifest_rel = "xlsx_workbook/abc123/demo_manifest.json"

    rows_payload = {
        "version": "module2-xlsx-sheet-rows-v2",
        "sheet_name": "空气质量监测",
        "headers": ["城市", "时间", "AQI"],
        "rows": [
            [
                1,
                2,
                [
                    [1, "济南市", "xlsx_t1_r2_c1", [1, 0, 0, 0, 0]],
                    [2, "2025-11-25 09:00:00", "xlsx_t1_r2_c2", [1, 0, 0, 0, 0]],
                    [3, "52", "xlsx_t1_r2_c3", [1, 0, 0, 0, 0], 52.0],
                ],
            ],
            [
                2,
                3,
                [
                    [1, "青岛市", "xlsx_t1_r3_c1", [1, 0, 0, 0, 0]],
                    [2, "2025-11-25 10:00:00", "xlsx_t1_r3_c2", [1, 0, 0, 0, 0]],
                    [3, "48", "xlsx_t1_r3_c3", [1, 0, 0, 0, 0], 48.0],
                ],
            ],
        ],
    }
    manifest_payload = {
        "version": "module2-xlsx-workbook-v1",
        "file_name": "2025年空气质量监测数据.xlsx",
        "sheet_count": 1,
        "source_total_rows": 20000,
        "sheets": [
            {
                "sheet_index": 1,
                "sheet_name": "空气质量监测",
                "headers": ["城市", "时间", "AQI"],
                "source_nonempty_row_count": 20000,
                "rows_artifact_path": rows_rel,
            }
        ],
    }

    (sheet_dir / "demo_rows.json").write_text(json.dumps(rows_payload, ensure_ascii=False), encoding="utf-8")
    (artifact_root / "xlsx_workbook" / "abc123" / "demo_manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setenv("SMART_DOC_FLOW_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("MODULE2_ARTIFACT_ROOT_DIR", str(artifact_root))

    doc = {
        "file_name": "demo.xlsx",
        "diagnostics": {
            "xlsx_workbook_manifest_path": manifest_rel,
        },
    }

    corpus = _compose_document_text(doc)

    assert "工作簿文件：2025年空气质量监测数据.xlsx" in corpus
    assert "工作表：空气质量监测" in corpus
    assert "工作表字段：城市，时间，AQI" in corpus
    assert "城市为济南市，时间为2025-11-25 09:00:00，AQI为52" in corpus
    assert "xlsx_t1_r2_c1" not in corpus
