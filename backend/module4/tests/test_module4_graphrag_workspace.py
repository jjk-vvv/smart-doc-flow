from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag_workspace import GraphRAGWorkspaceBuilder, WorkspaceSourceFile
from app.services.neo4j_graph import Neo4jSettings
from app.services.oneapi_runtime import GraphRAGRuntimeSettings
from app.services.prompt_registry import PromptRegistry


def _runtime(tmp_path: Path) -> GraphRAGRuntimeSettings:
    return GraphRAGRuntimeSettings(
        module4_root=tmp_path,
        workspaces_root=(tmp_path / "workspaces").resolve(),
        prompt_assets_root=(MODULE4_DIR / "assets" / "prompts").resolve(),
        api_base="http://oneapi.example/v1",
        chat_api_key="chat-secret",
        chat_model="qwen-turbo",
        embedding_api_key="embed-secret",
        embedding_model="text-embedding-v1",
        entity_types=["organization", "person", "geo", "event", "policy", "indicator"],
    )


def test_workspace_builder_materializes_workspace_assets(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    registry = PromptRegistry(asset_root=runtime.prompt_assets_root)
    neo4j = Neo4jSettings(
        uri="neo4j+s://example.databases.neo4j.io:7687",
        username="neo4j",
        password="password",
        database="neo4j",
    )
    builder = GraphRAGWorkspaceBuilder(runtime=runtime, prompt_registry=registry, neo4j=neo4j)

    result = builder.prepare_workspace(
        tenant_id="default",
        batch_id="batch-001",
        source="module2-upload",
        source_batch_key="batchkey001",
        files=[
            WorkspaceSourceFile(
                file_name="示例统计公报.pdf",
                file_hash="abc1234def5678",
                text_content="2024年地区生产总值增长5.2%，由市统计局发布。",
                source_kind="upload",
                artifact_path="module2/originals/sample.pdf",
                artifact_url="/extract/artifact/module2/originals/sample.pdf",
            )
        ],
    )

    assert result.workspace_dir.exists()
    assert result.env_path.exists()
    assert result.settings_path.exists()
    assert result.manifest_path.exists()
    assert (result.prompt_dir / "entity_extraction.txt").exists()

    env_text = result.env_path.read_text(encoding="utf-8")
    assert "GRAPHRAG_API_BASE=http://oneapi.example/v1" in env_text
    assert "NEO4J_URI=neo4j+s://example.databases.neo4j.io:7687" in env_text

    settings_text = result.settings_path.read_text(encoding="utf-8")
    assert 'prompt: "prompts/entity_extraction.txt"' in settings_text
    assert 'entity_types: ["organization", "person", "geo", "event", "policy", "indicator"]' in settings_text

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "prepared"
    assert manifest["batch_id"] == "batch-001"
    assert manifest["files"][0]["text_length"] > 0
    assert manifest["files"][0]["normalization_status"] == "success"


def test_workspace_builder_rejects_empty_text_inputs(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    builder = GraphRAGWorkspaceBuilder(
        runtime=runtime,
        prompt_registry=PromptRegistry(asset_root=runtime.prompt_assets_root),
        neo4j=Neo4jSettings(uri="", username="", password="", database="neo4j"),
    )

    with pytest.raises(ValueError, match="Normalized text is empty"):
        builder.prepare_workspace(
            tenant_id="default",
            batch_id="batch-001",
            source="module2-upload",
            source_batch_key="batchkey001",
            files=[
                WorkspaceSourceFile(
                    file_name="empty.txt",
                    file_hash="deadbeef",
                    text_content="   ",
                )
            ],
        )
