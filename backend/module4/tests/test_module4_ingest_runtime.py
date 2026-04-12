from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag.workspace import WorkspaceBuildResult  # noqa: E402
from app.services.ingestion.runtime import (  # noqa: E402
    _collect_graphrag_artifact_stage_status,
    DocumentGraphBuildError,
    Module4IngestRuntimeHelpers,
    process_document,
)


@dataclass
class _FakeStorage:
    reset_calls: int = 0

    async def reset_graph_file_scope(self, **_: Any) -> None:
        self.reset_calls += 1


class _FailingIndexer:
    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    def run(self, _: Path) -> Any:
        raise RuntimeError("index failed for test")

    def inspect_output(self, _: Path) -> Any:
        output_dir = self.workspace_dir / "output" / "latest"
        artifacts_dir = output_dir / "artifacts"
        reports_dir = output_dir / "reports"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        return SimpleNamespace(
            output_dir=str(output_dir),
            artifacts_dir=str(artifacts_dir),
            reports_dir=str(reports_dir),
            log_path=str(self.workspace_dir / "graphrag-index.log"),
            skipped_workflows=[],
        )


class _FakeWorkspaceBuilder:
    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    def prepare_workspace(self, **_: Any) -> WorkspaceBuildResult:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.workspace_dir / "workspace_manifest.json"
        manifest_path.write_text(json.dumps({"status": "prepared"}), encoding="utf-8")
        env_path = self.workspace_dir / ".env"
        settings_path = self.workspace_dir / "settings.yaml"
        env_path.write_text("", encoding="utf-8")
        settings_path.write_text("", encoding="utf-8")
        return WorkspaceBuildResult(
            tenant_id="tenant-a",
            batch_id="batch-a",
            workspace_id="workspace-a",
            workspace_dir=self.workspace_dir,
            env_path=env_path,
            settings_path=settings_path,
            manifest_path=manifest_path,
            input_dir=self.workspace_dir / "input",
            prompt_dir=self.workspace_dir / "prompts",
            files=[{"input_txt": str(self.workspace_dir / "input" / "001_doc.txt")}],
        )


def _helpers(workspace_builder: _FakeWorkspaceBuilder, indexer: _FailingIndexer) -> Module4IngestRuntimeHelpers:
    return Module4IngestRuntimeHelpers(
        default_tenant=lambda: "tenant-a",
        now_utc=lambda: datetime.utcnow(),
        risk_key=lambda value: f"risk-{hash(value)}",
        workspace_builder_getter=lambda: workspace_builder,
        graphrag_indexer_getter=lambda: indexer,
    )


def test_process_document_default_strict_mode_skips_partial_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    builder = _FakeWorkspaceBuilder(workspace_dir)
    indexer = _FailingIndexer(workspace_dir)
    storage = _FakeStorage()
    partial_called = {"value": False}

    async def _fake_partial_import(**_: Any) -> dict[str, Any] | None:
        partial_called["value"] = True
        return {"nodes": 1, "edges": 1}

    monkeypatch.delenv("MODULE4_GRAPHRAG_ALLOW_PARTIAL_IMPORT", raising=False)
    monkeypatch.setattr(
        "app.services.ingestion.runtime._import_partial_artifacts_after_index_failure",
        _fake_partial_import,
    )

    async def _run() -> None:
        with pytest.raises(DocumentGraphBuildError):
            await process_document(
                storage=storage,
                helpers=_helpers(builder, indexer),
                tenant_id="tenant-a",
                batch_id="batch-a",
                graph_file_id=None,
                doc={"file_name": "doc.txt", "text_corpus": "测试语料"},
            )

    asyncio.run(_run())
    assert partial_called["value"] is False
    assert storage.reset_calls == 0


def test_process_document_allows_partial_fallback_only_when_opted_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    builder = _FakeWorkspaceBuilder(workspace_dir)
    indexer = _FailingIndexer(workspace_dir)
    storage = _FakeStorage()
    partial_called = {"value": False}

    async def _fake_partial_import(**_: Any) -> dict[str, Any] | None:
        partial_called["value"] = True
        return {
            "nodes": 3,
            "edges": 2,
            "alerts": 0,
            "evidence": 1,
            "workspace": {"workspace_id": "workspace-a"},
            "index": {"output_dir": str(workspace_dir / "output" / "latest")},
            "import_summary": {"mode": "partial"},
            "graph_build_mode": "graphrag_partial",
            "artifact_stage_status": {"partial_ready": True},
        }

    monkeypatch.setenv("MODULE4_GRAPHRAG_ALLOW_PARTIAL_IMPORT", "1")
    monkeypatch.setattr(
        "app.services.ingestion.runtime._import_partial_artifacts_after_index_failure",
        _fake_partial_import,
    )

    async def _run() -> dict[str, Any]:
        return await process_document(
            storage=storage,
            helpers=_helpers(builder, indexer),
            tenant_id="tenant-a",
            batch_id="batch-a",
            graph_file_id=None,
            doc={"file_name": "doc.txt", "text_corpus": "测试语料"},
        )

    result = asyncio.run(_run())
    assert partial_called["value"] is True
    assert result["graph_build_mode"] == "graphrag_partial"
    assert "diagnostics" in result


def test_collect_graphrag_artifact_stage_status_accepts_v3_artifact_names(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    artifacts_dir = workspace_dir / "output" / "latest" / "artifacts"
    reports_dir = workspace_dir / "output" / "latest" / "reports"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    for name in (
        "text_units.parquet",
        "entities.parquet",
        "relationships.parquet",
        "communities.parquet",
        "community_reports.parquet",
    ):
        (artifacts_dir / name).write_text("stub", encoding="utf-8")

    status = _collect_graphrag_artifact_stage_status(
        workspace_dir=workspace_dir,
        output_dir=workspace_dir / "output" / "latest",
        artifacts_dir=artifacts_dir,
        reports_dir=reports_dir,
    )

    assert status["full_ready"] is True
    assert status["partial_ready"] is True
    assert status["stages"]["create_base_text_units"]["matched_artifact"] == "text_units.parquet"
    assert status["stages"]["create_final_entities"]["matched_artifact"] == "entities.parquet"
    assert status["stages"]["create_final_relationships"]["matched_artifact"] == "relationships.parquet"


def test_collect_graphrag_artifact_stage_status_marks_partial_when_only_partial_v3_artifacts_exist(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    artifacts_dir = workspace_dir / "output" / "latest" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    (artifacts_dir / "text_units.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "entities.parquet").write_text("stub", encoding="utf-8")

    status = _collect_graphrag_artifact_stage_status(
        workspace_dir=workspace_dir,
        output_dir=workspace_dir / "output" / "latest",
        artifacts_dir=artifacts_dir,
        reports_dir=None,
    )

    assert status["partial_ready"] is True
    assert status["full_ready"] is False
    assert status["stages"]["create_final_relationships"]["exists"] is False
