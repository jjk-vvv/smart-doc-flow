from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


fusion_routes = import_module("app.modules.module3.api.endpoints.fusion")


def test_require_run_output_path_prefers_output_file_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output_path = (tmp_path / "result.xlsx").resolve()
    output_path.write_bytes(b"test")

    monkeypatch.setattr(
        fusion_routes,
        "load_run_record",
        lambda run_id, owner_id=None: {
            "run_id": run_id,
            "output_file_id": "fa_test",
            "output_name": "result.xlsx",
        },
    )
    monkeypatch.setattr(
        fusion_routes,
        "resolve_file_for_owner",
        lambda file_id, owner_id: ({"file_id": file_id}, output_path),
    )

    _, resolved = fusion_routes._require_run_output_path("run_1", "tenant-a")
    assert resolved == output_path


def test_require_run_output_path_raises_when_output_file_asset_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        fusion_routes,
        "load_run_record",
        lambda run_id, owner_id=None: {
            "run_id": run_id,
            "output_file_id": "fa_missing",
            "output_name": "result.xlsx",
        },
    )

    def _missing(file_id: str, owner_id: str):
        raise FileNotFoundError("missing file asset")

    monkeypatch.setattr(fusion_routes, "resolve_file_for_owner", _missing)

    with pytest.raises(HTTPException) as exc_info:
        fusion_routes._require_run_output_path("run_2", "tenant-a")

    assert exc_info.value.status_code == 404


def test_require_run_output_path_raises_when_missing_output_file_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fusion_routes,
        "load_run_record",
        lambda run_id, owner_id=None: {
            "run_id": run_id,
            "output_file_id": "",
            "output_name": "",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        fusion_routes._require_run_output_path("run_3", "tenant-a")

    assert exc_info.value.status_code == 409
