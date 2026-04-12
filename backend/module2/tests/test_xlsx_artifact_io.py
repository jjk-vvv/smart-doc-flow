from __future__ import annotations

import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.core.format.xlsx_artifact_io import (
    load_xlsx_sheet_payload_for_table,
    load_xlsx_sheet_rows_artifact,
)
from app.runtime.artifact_support_runtime import ArtifactSupportRuntime


class _Logger:
    def warning(self, *args, **kwargs) -> None:
        return None


def test_load_xlsx_sheet_rows_artifact_inflates_compact_v2_rows(tmp_path: Path) -> None:
    artifact_path = tmp_path / "sheet_rows.json"
    artifact_path.write_text(
        json.dumps(
            {
                "version": "module2-xlsx-sheet-rows-v2",
                "file_name": "demo.xlsx",
                "file_hash": "abc123",
                "sheet_index": 1,
                "sheet_name": "Sheet1",
                "headers": ["姓名", "年龄"],
                "rows": [
                    [1, 2, [[1, "张三", "xlsx_t1_r2_c1", [1.0, 0.0, 0.0, 0.1, 0.1]], [2, "18", "xlsx_t1_r2_c2", [1.0, 0.1, 0.0, 0.1, 0.1], 18.0]]]
                ],
                "source_max_row": 10,
                "source_max_col": 2,
                "source_used_col_count": 2,
                "source_nonempty_row_count": 1,
                "source_nonempty_cell_count": 2,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )

    payload = load_xlsx_sheet_rows_artifact(str(artifact_path))

    assert payload["header_meta"][0]["name"] == "姓名"
    assert payload["rows"][0]["row_index"] == 1
    assert payload["rows"][0]["source_row_index"] == 2
    assert payload["rows"][0]["cells"][0]["header"] == "姓名"
    assert payload["rows"][0]["cells"][1]["numeric_value"] == 18.0

    table_payload = load_xlsx_sheet_payload_for_table({"xlsx_sheet_rows_artifact_path": str(artifact_path)})
    assert table_payload["rows"][0]["cells"][1]["text"] == "18"


def test_write_json_artifact_serializes_compact_json(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: artifact_root,
        logger=_Logger(),
    )

    fragment, _ = runtime.write_json_artifact(
        payload={"alpha": 1, "beta": {"x": 2}},
        file_name="demo",
        sub_dir="json",
    )

    content = (artifact_root / fragment).read_text(encoding="utf-8")
    assert content == '{"alpha":1,"beta":{"x":2}}'
