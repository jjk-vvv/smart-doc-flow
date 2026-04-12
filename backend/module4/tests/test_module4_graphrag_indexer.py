from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag.indexer import GraphRAGIndexer
from app.services.graphrag.indexer import GraphRAGIndexError
from app.services.query.neo4j import Neo4jSettings
from app.services.graphrag.settings import GraphRAGRuntimeSettings


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
    assert "MODULE4_GRAPHRAG_API_BASE" in probe.env_mapping["runtime"]
    assert probe.runtime_profile["indexing_method"] == "standard"


def test_indexer_prefers_local_module4_venv_for_generic_python(monkeypatch, tmp_path: Path) -> None:
    local_python = tmp_path / ".venv" / "Scripts" / "python.exe"
    local_python.parent.mkdir(parents=True)
    local_python.write_text("", encoding="utf-8")
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", "python")
    monkeypatch.setattr("app.services.graphrag.indexer._repo_venv_python", lambda: local_python)

    indexer = GraphRAGIndexer()

    assert Path(indexer.python_bin) == local_python


def test_indexer_probe_marks_runtime_unready_when_tiktoken_encoding_check_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_API_BASE", "http://oneapi.example/v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_API_KEY", "chat-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_MODEL", "qwen-turbo")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY", "embed-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_MODEL", "text-embedding-v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_PROMPTS_ROOT", str((MODULE4_DIR / "assets" / "prompts").resolve()))
    monkeypatch.setattr("app.services.graphrag.indexer._python_supports_module", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr(
        "app.services.graphrag.indexer._python_runtime_details",
        lambda *_args, **_kwargs: ({"python": "3.11.0"}, False, "MemoryError: cl100k_base"),
    )

    runtime = GraphRAGRuntimeSettings.from_env(module4_root=tmp_path)
    indexer = GraphRAGIndexer()
    probe = indexer.probe(
        runtime=runtime,
        neo4j=Neo4jSettings(uri="", username="", password="", database="neo4j"),
        check_remote=False,
    )

    assert probe.ready is False
    assert probe.tiktoken_encoding_ready is False
    assert "MemoryError" in (probe.tiktoken_encoding_error_message or "")


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

    monkeypatch.setattr("app.services.graphrag.indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    result = indexer.run(workspace_dir)

    assert result.output_dir == output_dir
    assert result.artifacts_dir == artifacts_dir
    assert result.reports_dir == reports_dir


def test_indexer_run_includes_non_standard_method_from_workspace_env(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    output_dir = workspace_dir / "output" / "20260101-000000"
    artifacts_dir = output_dir / "artifacts"
    reports_dir = output_dir / "reports"
    artifacts_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    (artifacts_dir / "create_final_documents.parquet").write_text("stub", encoding="utf-8")
    (workspace_dir / ".env").write_text("GRAPHRAG_INDEXING_METHOD=fast\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = list(args[0])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.services.graphrag.indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    result = indexer.run(workspace_dir)

    cmd = captured.get("cmd")
    assert isinstance(cmd, list)
    assert "--method" in cmd
    assert "fast" in cmd
    assert result.command == cmd


def test_indexer_retries_without_community_reports_when_json_output_is_unstable(
    monkeypatch, tmp_path: Path
) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / ".env").write_text("GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS=1\n", encoding="utf-8")
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

    monkeypatch.setattr("app.services.graphrag.indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    result = indexer.run(workspace_dir)

    assert calls["count"] == 2
    assert result.skipped_workflows in (["create_community_reports"], ["create_final_community_reports"])
    assert result.artifacts_dir == workspace_dir / "output" / "20260101-000000" / "artifacts"
    settings_text = (workspace_dir / "settings.yaml").read_text(encoding="utf-8")
    assert (
        'skip_workflows: ["create_community_reports"]' in settings_text
        or 'skip_workflows: ["create_final_community_reports"]' in settings_text
    )


def test_indexer_does_not_retry_without_explicit_opt_in(monkeypatch, tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True)
    (workspace_dir / ".env").write_text("", encoding="utf-8")
    (workspace_dir / "settings.yaml").write_text(
        "skip_workflows: []\n",
        encoding="utf-8",
    )

    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        log_file = kwargs["stdout"]
        log_file.write("error generating community report\n")
        log_file.write("create_community_reports\n")
        log_file.write("Failed to generate valid JSON output\n")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr("app.services.graphrag.indexer.subprocess.run", fake_run)
    monkeypatch.setenv("MODULE4_GRAPHRAG_PYTHON_BIN", sys.executable)

    indexer = GraphRAGIndexer()
    with pytest.raises(GraphRAGIndexError) as exc_info:
        indexer.run(workspace_dir)

    assert calls["count"] == 1
    assert exc_info.value.category == "index_process_failed"


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
