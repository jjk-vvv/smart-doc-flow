from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "core"
        / "table"
        / "ocr_table_utils.py"
    )
    module_name = "_smart_doc_flow_module2_ocr_table_utils"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ocr_table_utils_module = _load_module()
OcrTableUtils = ocr_table_utils_module.OcrTableUtils


def _build_utils(**overrides):
    defaults = dict(
        ocr_max_pages=4,
        ocr_front_scan_pages=6,
        ocr_extra_sample_pages=2,
        ocr_cue_neighbor=1,
        ocr_cue_max_pages=8,
        ocr_max_scan_pages=10,
        ocr_cue_boost_max_pages=8,
        ocr_min_coverage_ratio=0.2,
        ocr_min_scan_pages=4,
        visual_weak_table_min=4,
        ocr_table_min_quality=0.52,
        ocr_line_aug_max_extra_cue_pages=3,
        ocr_uncovered_line_aug_pages=4,
        table_merge_enable=True,
        ocr_table_min_rows=2,
        ocr_table_row_gap=0.08,
        ocr_table_col_tol=0.04,
        looks_like_table_cue_text=lambda text: ("表" in text) or ("table" in str(text).lower()),
        merge_same_page_tables=lambda tables: tables,
        merge_cross_page_tables=lambda tables: tables,
    )
    defaults.update(overrides)
    return OcrTableUtils(**defaults)


def test_ocr_table_utils_build_ocr_page_indices_keeps_front_pages_and_cues() -> None:
    utils = _build_utils()

    page_indices = utils.build_ocr_page_indices(12, cue_pages=[9])

    assert page_indices[:4] == [0, 1, 2, 3]
    assert 8 in page_indices
    assert 9 in page_indices
    assert 10 in page_indices
    assert len(page_indices) <= 10


def test_ocr_table_utils_split_detect_and_select_pages() -> None:
    utils = _build_utils()
    page_lines = {
        1: ["表 1 总览", "名称    数值    单位"],
        2: ["正文内容"],
        3: ["Table 2 metrics", "A  B  10  11"],
        4: ["图 1 趋势"],
        5: ["表 3 统计"],
    }
    base_tables = [{"page": 3, "quality": 0.6}]

    assert utils.split_table_line("A    B    10    11") == ["A", "B", "10", "11"]
    assert utils.is_table_line("A    B    10    11", ["A", "B", "10", "11"]) is True

    selected = utils.select_line_augmentation_pages(page_lines, base_tables, cue_pages=[4])

    assert 2 in selected
    assert 3 in selected
    assert 4 in selected
    assert 5 in selected


def test_ocr_table_utils_signature_and_augment_skip_duplicates() -> None:
    utils = _build_utils()
    table_a = {
        "page": 1,
        "headers": ["名称", "数值"],
        "row_count": 2,
        "col_count": 2,
        "rows": [{"cells": [{"text": "温度"}, {"text": "25"}]}],
    }
    table_dup = {
        "page": 1,
        "headers": ["名称", "数值"],
        "row_count": 2,
        "col_count": 2,
        "rows": [{"cells": [{"text": "温度"}, {"text": "25"}]}],
    }
    table_b = {
        "page": 1,
        "headers": ["名称", "峰值"],
        "row_count": 3,
        "col_count": 2,
        "rows": [{"cells": [{"text": "压力"}, {"text": "11"}]}],
    }

    merged = utils.augment_with_line_tables([table_a], [table_dup, table_b])

    assert utils.table_signature(table_a) == utils.table_signature(table_dup)
    assert len(merged) == 2


def test_ocr_table_utils_false_table_and_quality_helpers() -> None:
    utils = _build_utils()
    toc_rows = [
        {"cells": [{"col_index": 1, "text": "第一章 总则"}, {"col_index": 2, "text": "1"}]},
        {"cells": [{"col_index": 1, "text": "第二章 说明"}, {"col_index": 2, "text": "3"}]},
        {"cells": [{"col_index": 1, "text": "第三章 附录"}, {"col_index": 2, "text": "8"}]},
        {"cells": [{"col_index": 1, "text": "第四章 参考"}, {"col_index": 2, "text": "10"}]},
        {"cells": [{"col_index": 1, "text": "第五章 结束"}, {"col_index": 2, "text": "12"}]},
        {"cells": [{"col_index": 1, "text": "第六章 说明"}, {"col_index": 2, "text": "15"}]},
        {"cells": [{"col_index": 1, "text": "第七章 扩展"}, {"col_index": 2, "text": "18"}]},
        {"cells": [{"col_index": 1, "text": "第八章 总结"}, {"col_index": 2, "text": "22"}]},
    ]
    real_rows = [
        {"cells": [{"col_index": 1, "text": "2024"}, {"col_index": 2, "text": "25"}, {"col_index": 3, "text": "13"}]},
        {"cells": [{"col_index": 1, "text": "2025"}, {"col_index": 2, "text": "27"}, {"col_index": 3, "text": "14"}]},
        {"cells": [{"col_index": 1, "text": "2026"}, {"col_index": 2, "text": "29"}, {"col_index": 3, "text": "15"}]},
    ]
    quality_group = [
        {"cells": [{"text": "2024", "x_center": 0.2}, {"text": "25", "x_center": 0.5}, {"text": "13", "x_center": 0.8}]},
        {"cells": [{"text": "2025", "x_center": 0.2}, {"text": "27", "x_center": 0.5}, {"text": "14", "x_center": 0.8}]},
        {"cells": [{"text": "2026", "x_center": 0.2}, {"text": "29", "x_center": 0.5}, {"text": "15", "x_center": 0.8}]},
    ]
    anchors = [0.2, 0.5, 0.8]
    cells = [
        {"text": "2024", "x_center": 0.2, "y_center": 0.1, "bbox": [1.0, 0.1, 0.0, 0.1, 0.02]},
        {"text": "2024", "x_center": 0.201, "y_center": 0.101, "bbox": [1.0, 0.1, 0.0, 0.1, 0.02]},
        {"text": "2025", "x_center": 0.5, "y_center": 0.2, "bbox": [1.0, 0.4, 0.0, 0.1, 0.02]},
    ]

    assert utils.looks_like_false_table(["目录", "页码"], toc_rows, runtime_page_count=20) is True
    assert utils.looks_like_false_table(["年份", "温度", "压力"], real_rows, runtime_page_count=20) is False
    assert utils.table_quality_score(quality_group, anchors) > 0.7
    assert len(utils.dedupe_ocr_cells(cells)) == 2
