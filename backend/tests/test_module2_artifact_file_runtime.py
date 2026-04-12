from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response


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


artifact_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "artifact_file_runtime.py"],
    "_smart_doc_flow_module2_artifact_file_runtime",
)

Module2ArtifactFileRuntime = artifact_runtime_module.Module2ArtifactFileRuntime


def test_module2_artifact_file_runtime_resolves_safe_paths_and_absolute_storage(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    runtime = Module2ArtifactFileRuntime(artifact_root_factory=lambda: artifact_root)

    target = runtime.safe_artifact_path("nested/demo.txt")
    assert target == (artifact_root / "nested" / "demo.txt").resolve()
    assert runtime.absolute_storage_path("nested/demo.txt") == str(target)
    assert runtime.absolute_storage_path("") == ""


def test_module2_artifact_file_runtime_rejects_escape_path(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    runtime = Module2ArtifactFileRuntime(artifact_root_factory=lambda: artifact_root)

    try:
        runtime.safe_artifact_path("../outside.txt")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Invalid artifact path"
    else:
        raise AssertionError("expected HTTPException for invalid artifact path")


def test_module2_artifact_file_runtime_serves_head_and_get_requests(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    target = artifact_root / "layout" / "preview.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-1.4\npreview\n")
    runtime = Module2ArtifactFileRuntime(artifact_root_factory=lambda: artifact_root)

    head_response = runtime.serve_artifact(
        path_fragment="layout/preview.pdf",
        request_method="HEAD",
        not_found_detail="missing",
        default_media_type="application/pdf",
    )
    get_response = runtime.serve_artifact(
        path_fragment="layout/preview.pdf",
        request_method="GET",
        not_found_detail="missing",
        default_media_type="application/pdf",
    )

    assert isinstance(head_response, Response)
    assert head_response.headers["Content-Type"] == "application/pdf"
    assert head_response.headers["Content-Length"] == str(target.stat().st_size)
    assert isinstance(get_response, FileResponse)
    assert Path(get_response.path).resolve() == target.resolve()
    assert get_response.media_type == "application/pdf"


def test_module2_artifact_file_runtime_raises_not_found_for_missing_file(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    runtime = Module2ArtifactFileRuntime(artifact_root_factory=lambda: artifact_root)

    try:
        runtime.serve_artifact(
            path_fragment="missing/file.txt",
            request_method="GET",
            not_found_detail="Artifact not found: missing/file.txt",
            default_media_type="application/octet-stream",
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Artifact not found: missing/file.txt"
    else:
        raise AssertionError("expected HTTPException for missing artifact")
