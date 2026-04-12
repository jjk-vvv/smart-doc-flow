from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag.prompts import PromptRegistry
from app.services.graphrag.settings import GraphRAGRuntimeSettings
from app.services.graphrag.workspace import GraphRAGWorkspaceBuilder, WorkspaceSourceFile
from app.services.query.neo4j import Neo4jSettings


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
                file_name="sample_report.txt",
                file_hash="abc1234def5678",
                text_content="2024 regional output increased 5.2 percent according to the statistics bureau.",
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
    assert (result.prompt_dir / "extract_graph.txt").exists()
    assert (result.prompt_dir / "community_report_text.txt").exists()
    assert (result.prompt_dir / "local_search_system_prompt.txt").exists()
    assert (result.prompt_dir / "global_search_map_system_prompt.txt").exists()
    assert (result.prompt_dir / "drift_search_system_prompt.txt").exists()
    assert (result.prompt_dir / "basic_search_system_prompt.txt").exists()

    env_text = result.env_path.read_text(encoding="utf-8")
    assert "GRAPHRAG_API_BASE=http://oneapi.example/v1" in env_text
    assert "NEO4J_URI=neo4j+s://example.databases.neo4j.io:7687" in env_text
    assert "GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE=prompts/local_search_system_prompt.txt" in env_text

    settings_text = result.settings_path.read_text(encoding="utf-8")
    assert 'prompt: "prompts/extract_graph.txt"' in settings_text
    assert 'community_reports:\n  completion_model_id: default_chat_model' in settings_text
    assert 'graph_prompt: "prompts/community_report_graph.txt"' in settings_text
    assert 'text_prompt: "prompts/community_report_text.txt"' in settings_text
    assert 'entity_types: ["organization", "person", "geo", "event", "policy", "indicator"]' in settings_text
    assert 'local_search:\n  completion_model_id: default_chat_model' in settings_text
    assert 'prompt: "prompts/local_search_system_prompt.txt"' in settings_text
    assert 'map_prompt: "prompts/global_search_map_system_prompt.txt"' in settings_text
    assert 'reduce_prompt: "prompts/global_search_reduce_system_prompt.txt"' in settings_text
    assert 'knowledge_prompt: "prompts/global_search_knowledge_system_prompt.txt"' in settings_text
    assert 'prompt: "prompts/drift_search_system_prompt.txt"' in settings_text
    assert 'reduce_prompt: "prompts/drift_search_reduce_prompt.txt"' in settings_text
    assert 'prompt: "prompts/basic_search_system_prompt.txt"' in settings_text

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "prepared"
    assert manifest["batch_id"] == "batch-001"
    assert manifest["runtime_profile"]["indexing_method"] == "standard"
    assert "MODULE4_GRAPHRAG_API_BASE" in manifest["env_mapping"]["runtime"]
    assert "MODULE4_GRAPHRAG_LOCAL_SEARCH_PROMPT_FILE" in manifest["env_mapping"]["prompts"]
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


def test_workspace_builder_renders_workflows_and_skip_workflows(tmp_path: Path) -> None:
    runtime = GraphRAGRuntimeSettings(
        module4_root=tmp_path,
        workspaces_root=(tmp_path / "workspaces").resolve(),
        prompt_assets_root=(MODULE4_DIR / "assets" / "prompts").resolve(),
        api_base="http://oneapi.example/v1",
        chat_api_key="chat-secret",
        chat_model="qwen-turbo",
        embedding_api_key="embed-secret",
        embedding_model="text-embedding-v1",
        workflows=["create_base_text_units", "extract_graph"],
        skip_workflows=["generate_text_embeddings"],
        indexing_method="fast",
    )
    builder = GraphRAGWorkspaceBuilder(
        runtime=runtime,
        prompt_registry=PromptRegistry(asset_root=runtime.prompt_assets_root),
        neo4j=Neo4jSettings(uri="", username="", password="", database="neo4j"),
    )

    result = builder.prepare_workspace(
        tenant_id="default",
        batch_id="batch-002",
        source="module2-upload",
        source_batch_key="batchkey002",
        files=[
            WorkspaceSourceFile(
                file_name="demo.txt",
                file_hash="abc1234def5678",
                text_content="demo text",
            )
        ],
    )

    settings_text = result.settings_path.read_text(encoding="utf-8")
    assert 'workflows: ["create_base_text_units", "extract_graph"]' in settings_text
    assert 'skip_workflows: ["generate_text_embeddings"]' in settings_text
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["runtime_profile"]["indexing_method"] == "fast"
