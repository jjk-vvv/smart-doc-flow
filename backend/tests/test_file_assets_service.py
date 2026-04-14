from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _reload_service_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("FILE_ASSETS_ROOT_DIR", str((tmp_path / "file-assets").resolve()))
    module = importlib.import_module("app.modules.file_assets.service")
    return importlib.reload(module)


def test_file_assets_register_and_preview(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = _reload_service_module(monkeypatch, tmp_path)

    source_file = (tmp_path / "sample.txt").resolve()
    source_file.write_text("line1\nline2\nline3", encoding="utf-8")

    record = service.register_file(
        path=source_file,
        owner_id="tenant-a",
        source_module="module3",
        purpose="run_output",
        filename="out.txt",
    )

    assert record["file_id"].startswith("fa_")
    assert record["owner_id"] == "tenant-a"
    assert Path(record["path"]).resolve() == source_file

    resolved_record, resolved_path = service.resolve_file_for_owner(record["file_id"], "tenant-a")
    assert resolved_record["file_id"] == record["file_id"]
    assert resolved_path == source_file

    preview = service.build_preview_text_for_owner(record["file_id"], "tenant-a", max_lines=2, max_chars=1000)
    assert "line1" in preview
    assert "line2" in preview
    assert "line3" not in preview

    with pytest.raises(PermissionError):
        service.resolve_file_for_owner(record["file_id"], "tenant-b")


def test_file_assets_register_reuses_same_owner_and_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = _reload_service_module(monkeypatch, tmp_path)

    source_file = (tmp_path / "same.md").resolve()
    source_file.write_text("# title\n", encoding="utf-8")

    first = service.register_file(
        path=source_file,
        owner_id="tenant-a",
        source_module="module3",
        purpose="docset_source",
        filename="same.md",
    )
    second = service.register_file(
        path=source_file,
        owner_id="tenant-a",
        source_module="module3",
        purpose="docset_source",
        filename="same.md",
    )

    assert second["file_id"] == first["file_id"]


def test_file_assets_helpers_preview_support_and_urls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    service = _reload_service_module(monkeypatch, tmp_path)

    assert service.preview_support_for_suffix(".txt") == (True, None)
    assert service.preview_support_for_suffix("docx") == (True, None)

    unsupported_ok, unsupported_reason = service.preview_support_for_suffix(".pdf")
    assert unsupported_ok is False
    assert "not supported" in str(unsupported_reason or "").lower()

    links = service.build_file_asset_urls("fa_demo")
    assert links["download_url"] == "/download/fa_demo"
    assert links["preview_url"] == "/file-assets/fa_demo/preview"
