from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


run_service = import_module("app.modules.module3.services.run_service")


def test_resolve_docset_source_path_uses_file_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source_path = (tmp_path / "source.txt").resolve()
    source_path.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(
        run_service,
        "resolve_file_for_owner",
        lambda file_id, owner_id: ({"file_id": file_id, "owner_id": owner_id}, source_path),
    )

    resolved = run_service._resolve_docset_source_path(  # type: ignore[attr-defined]
        {"filename": "source.txt", "file_id": "fa_source"},
        "tenant-a",
    )
    assert resolved == source_path


def test_resolve_docset_source_path_rejects_missing_file_id() -> None:
    with pytest.raises(ValueError) as exc_info:
        run_service._resolve_docset_source_path({"filename": "source.txt"}, "tenant-a")  # type: ignore[attr-defined]

    assert "file_id is missing" in str(exc_info.value)


def test_resolve_template_path_uses_template_file_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    template_path = (tmp_path / "template.xlsx").resolve()
    template_path.write_bytes(b"demo")

    monkeypatch.setattr(
        run_service,
        "resolve_file_for_owner",
        lambda file_id, owner_id: ({"file_id": file_id, "owner_id": owner_id}, template_path),
    )

    resolved = run_service._resolve_template_path(  # type: ignore[attr-defined]
        {"filename": "template.xlsx", "template_file_id": "fa_tpl"},
        "tenant-a",
    )
    assert resolved == template_path


def test_resolve_template_path_rejects_missing_template_file_id() -> None:
    with pytest.raises(ValueError) as exc_info:
        run_service._resolve_template_path({"filename": "template.xlsx"}, "tenant-a")  # type: ignore[attr-defined]

    assert "Template file_id is missing" in str(exc_info.value)
