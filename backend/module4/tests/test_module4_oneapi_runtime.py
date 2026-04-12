from __future__ import annotations

import sys
from pathlib import Path


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.query.neo4j import Neo4jSettings
from app.services.graphrag.settings import GraphRAGRuntimeSettings


def test_runtime_settings_read_module4_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_API_BASE", "http://oneapi.example/v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_API_KEY", "chat-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_CHAT_MODEL", "qwen-turbo")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY", "embed-secret")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EMBEDDING_MODEL", "text-embedding-v1")
    monkeypatch.setenv("MODULE4_GRAPHRAG_PROMPTS_ROOT", "assets/prompts")
    monkeypatch.setenv("MODULE4_GRAPHRAG_WORKSPACES_ROOT", "workspaces")
    monkeypatch.setenv("MODULE4_GRAPHRAG_ENTITY_TYPES", "organization,person,geo,event,policy,indicator")
    monkeypatch.setenv("MODULE4_GRAPHRAG_EXTRACT_GRAPH_PROMPT_FILE", "extract_graph.txt")
    monkeypatch.setenv("MODULE4_GRAPHRAG_INDEXING_METHOD", "standard")
    monkeypatch.setenv("MODULE4_GRAPHRAG_WORKFLOWS", "create_base_text_units,extract_graph")
    monkeypatch.setenv("MODULE4_GRAPHRAG_SKIP_WORKFLOWS", "generate_text_embeddings")

    settings = GraphRAGRuntimeSettings.from_env(module4_root=tmp_path)

    assert settings.is_configured() is True
    assert settings.api_base == "http://oneapi.example/v1"
    assert settings.chat_model == "qwen-turbo"
    assert settings.embedding_model == "text-embedding-v1"
    assert settings.prompt_assets_root == (tmp_path / "assets" / "prompts").resolve()
    assert settings.workspaces_root == (tmp_path / "workspaces").resolve()
    assert settings.entity_types[-1] == "indicator"
    assert settings.workspace_env()["GRAPHRAG_CHAT_MODEL"] == "qwen-turbo"
    assert settings.indexing_method == "standard"
    assert settings.workflows == ["create_base_text_units", "extract_graph"]
    assert settings.skip_workflows == ["generate_text_embeddings"]
    assert settings.workspace_env()["GRAPHRAG_WORKFLOWS"] == "create_base_text_units,extract_graph"
    assert settings.workspace_env()["GRAPHRAG_SKIP_WORKFLOWS"] == "generate_text_embeddings"
    assert settings.env_mapping()["runtime"]["MODULE4_GRAPHRAG_INDEXING_METHOD"] == "GRAPHRAG_INDEXING_METHOD"


def test_neo4j_settings_read_module4_env(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_NEO4J_URI", "neo4j+s://example.databases.neo4j.io:7687")
    monkeypatch.setenv("MODULE4_NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("MODULE4_NEO4J_PASSWORD", "password")
    monkeypatch.setenv("MODULE4_NEO4J_DATABASE", "neo4j")

    settings = Neo4jSettings.from_env()

    assert settings.is_configured() is True
    assert settings.database == "neo4j"
    assert settings.workspace_env()["NEO4J_USERNAME"] == "neo4j"
