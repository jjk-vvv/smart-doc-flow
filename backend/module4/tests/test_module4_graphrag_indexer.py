from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag_indexer import GraphRAGIndexer
from app.services.neo4j_graph import Neo4jSettings
from app.services.oneapi_runtime import GraphRAGRuntimeSettings


def test_indexer_probe_reports_missing_python_binary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_API_BASE", "http://oneapi.example/v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_API_KEY", "chat-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_MODEL", "qwen-turbo")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY", "embed-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_MODEL", "text-embedding-v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_PROMPTS_ROOT", str((MODULE4_DIR / "assets" / "prompts").resolve()))
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", "python-does-not-exist-module4")

    runtime = GraphRAGRuntimeSettings.from_env(module4_root=tmp_path)
    indexer = GraphRAGIndexer()
    probe = indexer.probe(
        runtime=runtime,
        neo4j=Neo4jSettings(uri="", username="", password="", database="neo4j"),
        check_remote=False,
    )

    assert probe.ready is False
    assert probe.python_bin_exists is False
    assert probe.graphrag_module_available is False
    assert "Configured python executable not found" in (probe.module_error_message or "")
    assert probe.prompt_assets_ok is True


def test_indexer_run_accepts_root_level_artifacts_layout(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    output_dir = workspace_dir / "output"
    artifacts_dir = output_dir / "artifacts"
    reports_dir = output_dir / "reports"
    artifacts_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (workspace_dir / ".env").write_text("", encoding="utf-8")
    (artifacts_dir / "create_final_documents.parquet").write_text("stub", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.services.graphrag_indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    result = indexer.run(workspace_dir)

    assert result.output_dir == output_dir
    assert result.artifacts_dir == artifacts_dir
    assert result.reports_dir == reports_dir


def test_indexer_retries_without_community_reports_when_json_output_is_unstable(
    monkeypatch, tmp_path: Path
) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / ".env").write_text("", encoding="utf-8")
    (workspace_dir / "settings.yaml").write_text(
        "encoding_model: cl100k_base\nskip_workflows: []\n",
        encoding="utf-8",
    )

    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        log_file = kwargs["stdout"]
        if calls["count"] == 1:
            log_file.write("error generating community report\n")
            log_file.write("create_final_community_reports\n")
            log_file.write("Failed to generate valid JSON output\n")
            return SimpleNamespace(returncode=1)

        artifacts_dir = workspace_dir / "output" / "20260101-000000" / "artifacts"
        reports_dir = workspace_dir / "output" / "20260101-000000" / "reports"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "create_final_documents.parquet").write_text("stub", encoding="utf-8")
        log_file.write("retry success\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.services.graphrag_indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    result = indexer.run(workspace_dir)

    assert calls["count"] == 2
    assert result.skipped_workflows == ["create_final_community_reports"]
    assert result.artifacts_dir == workspace_dir / "output" / "20260101-000000" / "artifacts"
    assert 'skip_workflows: ["create_final_community_reports"]' in (
        workspace_dir / "settings.yaml"
    ).read_text(encoding="utf-8")


def test_indexer_inspect_output_recovers_partial_artifacts_layout(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    artifacts_dir = workspace_dir / "output" / "20260101-000000" / "artifacts"
    reports_dir = workspace_dir / "output" / "20260101-000000" / "reports"
    artifacts_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (artifacts_dir / "create_base_text_units.parquet").write_text("stub", encoding="utf-8")

    indexer = GraphRAGIndexer()
    result = indexer.inspect_output(workspace_dir)

    assert result.output_dir == workspace_dir / "output" / "20260101-000000"
    assert result.artifacts_dir == artifacts_dir
    assert result.reports_dir == reports_dir
