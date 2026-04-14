from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "runtime"
        / "artifact_support_runtime.py"
    )
    module_name = "_smart_doc_flow_module2_artifact_support_runtime"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


runtime_module = _load_module()
ArtifactSupportRuntime = runtime_module.ArtifactSupportRuntime


def test_artifact_support_runtime_writes_artifacts_and_builds_urls(tmp_path: Path) -> None:
    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: tmp_path / "artifacts",
        logger=logging.getLogger("test-artifact-support-runtime"),
    )

    fragment, url = runtime.write_artifact_bytes(
        data=b"hello",
        file_name="demo file.pdf",
        sub_dir="preview/pdf",
        ext=".pdf",
    )

    assert fragment.startswith("preview/pdf/demo_file_")
    assert url.startswith("/extract/artifact/preview/pdf/demo_file_")
    assert (tmp_path / "artifacts" / fragment).read_bytes() == b"hello"


def test_artifact_support_runtime_mirrors_external_file_into_linked_folder(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    outside_file = tmp_path / "outside data" / "图表 1.png"
    outside_file.parent.mkdir(parents=True, exist_ok=True)
    outside_file.write_bytes(b"png")

    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: artifact_root,
        logger=logging.getLogger("test-artifact-support-runtime"),
    )

    fragment = runtime.artifact_fragment_from_path(str(outside_file))

    assert fragment.startswith("linked/")
    mirrored = artifact_root / fragment
    assert mirrored.read_bytes() == b"png"


def test_artifact_support_runtime_persists_assistant_artifacts_and_resolves_trace_refs(tmp_path: Path) -> None:
    runtime = ArtifactSupportRuntime(
        artifact_root_factory=lambda: tmp_path / "artifacts",
        logger=logging.getLogger("test-artifact-support-runtime"),
    )

    payload_fragment, payload_url = runtime.persist_assistant_payload_artifact(
        file_name="demo.pdf",
        file_hash="abcdef1234567890",
        table_blocks=[{"table_id": "t1"}],
        figure_blocks=[{"figure_id": "f1"}],
    )
    markdown_fragment, markdown_url, manifest_fragment, manifest_url = runtime.persist_assistant1_source_markdown_artifact(
        file_name="demo.pdf",
        file_hash="abcdef1234567890",
        markdown_text="# Demo",
        track="VisualTrack",
    )

    payload_data = json.loads((tmp_path / "artifacts" / payload_fragment).read_text(encoding="utf-8"))
    manifest_data = json.loads((tmp_path / "artifacts" / manifest_fragment).read_text(encoding="utf-8"))

    assert payload_url == runtime.artifact_url_from_fragment(payload_fragment)
    assert payload_data["version"] == "module2-assistant-payload-v1"
    assert markdown_url == runtime.artifact_url_from_fragment(markdown_fragment)
    assert manifest_url == runtime.artifact_url_from_fragment(manifest_fragment)
    assert manifest_data["markdown_artifact_path"] == markdown_fragment

    resolved_fragment, resolved_url = runtime.resolve_trace_artifact_ref({"artifact_path": payload_fragment})
    assert resolved_fragment == payload_fragment
    assert resolved_url == payload_url

    direct_fragment, direct_url = runtime.resolve_trace_artifact_ref({"artifact_url": "/extract/artifact/direct/demo.pdf"})
    assert direct_fragment is None
    assert direct_url == "/extract/artifact/direct/demo.pdf"
