from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .neo4j_graph import Neo4jSettings
from .oneapi_runtime import GraphRAGRuntimeSettings
from .prompt_registry import PromptRegistry


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_segment(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "").strip()).strip("-._")
    return cleaned or fallback


def _safe_file_stem(file_name: str) -> str:
    stem = Path(str(file_name or "document")).stem
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", stem).strip("._- ")
    return cleaned or "document"


def _yaml_scalar(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list(values: List[str]) -> str:
    inner = ", ".join(json.dumps(str(item), ensure_ascii=False) for item in values)
    return f"[{inner}]"


def render_settings_yaml(
    runtime: GraphRAGRuntimeSettings,
    prompt_targets: Dict[str, Path],
) -> str:
    prompt_refs = {key: f"prompts/{path.name}" for key, path in prompt_targets.items()}
    return (
        "encoding_model: cl100k_base\n"
        "skip_workflows: []\n"
        "llm:\n"
        "  api_key: ${GRAPHRAG_CHAT_API_KEY}\n"
        "  type: openai_chat\n"
        "  model: ${GRAPHRAG_CHAT_MODEL}\n"
        "  model_supports_json: true\n"
        f"  max_tokens: {runtime.max_tokens}\n"
        "  api_base: ${GRAPHRAG_API_BASE}\n"
        "\n"
        "parallelization:\n"
        "  stagger: 0.3\n"
        "\n"
        "async_mode: threaded\n"
        "\n"
        "embeddings:\n"
        "  async_mode: threaded\n"
        "  llm:\n"
        "    api_key: ${GRAPHRAG_EMBEDDING_API_KEY}\n"
        "    type: openai_embedding\n"
        "    model: ${GRAPHRAG_EMBEDDING_MODEL}\n"
        "    api_base: ${GRAPHRAG_API_BASE}\n"
        "\n"
        "chunks:\n"
        f"  size: {runtime.chunk_size}\n"
        f"  overlap: {runtime.chunk_overlap}\n"
        "  group_by_columns: [id]\n"
        "\n"
        "input:\n"
        "  type: file\n"
        "  file_type: text\n"
        f"  base_dir: {_yaml_scalar(runtime.input_dir)}\n"
        "  file_encoding: utf-8\n"
        '  file_pattern: ".*\\\\.txt$"\n'
        "\n"
        "cache:\n"
        "  type: file\n"
        f"  base_dir: {_yaml_scalar(runtime.cache_dir)}\n"
        "\n"
        "storage:\n"
        "  type: file\n"
        f"  base_dir: {_yaml_scalar(runtime.storage_dir)}\n"
        "\n"
        "reporting:\n"
        "  type: file\n"
        f"  base_dir: {_yaml_scalar(runtime.reporting_dir)}\n"
        "\n"
        "entity_extraction:\n"
        f"  prompt: {_yaml_scalar(prompt_refs['entity_extraction'])}\n"
        f"  entity_types: {_yaml_list(runtime.entity_types)}\n"
        "  max_gleanings: 1\n"
        "\n"
        "summarize_descriptions:\n"
        f"  prompt: {_yaml_scalar(prompt_refs['summarize_descriptions'])}\n"
        "  max_length: 500\n"
        "\n"
        "claim_extraction:\n"
        f"  prompt: {_yaml_scalar(prompt_refs['claim_extraction'])}\n"
        '  description: "Any claims or facts that could be relevant to information discovery."\n'
        "  max_gleanings: 1\n"
        "\n"
        "community_reports:\n"
        f"  prompt: {_yaml_scalar(prompt_refs['community_report'])}\n"
        "  max_length: 2000\n"
        "  max_input_length: 8000\n"
        "\n"
        "cluster_graph:\n"
        f"  max_cluster_size: {runtime.cluster_max_size}\n"
        "\n"
        "embed_graph:\n"
        "  enabled: false\n"
        "\n"
        "umap:\n"
        "  enabled: false\n"
        "\n"
        "snapshots:\n"
        "  graphml: false\n"
        "  raw_entities: false\n"
        "  top_level_nodes: false\n"
    )


def render_workspace_env(
    runtime: GraphRAGRuntimeSettings,
    neo4j: Neo4jSettings,
    prompt_targets: Dict[str, Path],
) -> str:
    prompt_paths = {key: f"prompts/{path.name}" for key, path in prompt_targets.items()}
    rows: List[str] = []
    for key, value in runtime.workspace_env(prompt_paths=prompt_paths).items():
        rows.append(f"{key}={value}")
    for key, value in neo4j.workspace_env().items():
        rows.append(f"{key}={value}")
    rows.append("")
    return "\n".join(rows)


@dataclass(frozen=True)
class WorkspaceSourceFile:
    file_name: str
    file_hash: str
    text_content: str
    source_kind: str = "upload"
    original_path: str | None = None
    artifact_path: str | None = None
    artifact_url: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceBuildResult:
    tenant_id: str
    batch_id: str
    workspace_id: str
    workspace_dir: Path
    env_path: Path
    settings_path: Path
    manifest_path: Path
    input_dir: Path
    prompt_dir: Path
    files: List[Dict[str, Any]]


class GraphRAGWorkspaceBuilder:
    def __init__(
        self,
        runtime: GraphRAGRuntimeSettings | None = None,
        prompt_registry: PromptRegistry | None = None,
        neo4j: Neo4jSettings | None = None,
    ) -> None:
        self.runtime = runtime or GraphRAGRuntimeSettings.from_env()
        self.prompt_registry = prompt_registry or PromptRegistry(
            asset_root=self.runtime.prompt_assets_root,
            overrides=self.runtime.prompt_overrides(),
        )
        self.neo4j = neo4j or Neo4jSettings.from_env()

    def prepare_workspace(
        self,
        *,
        tenant_id: str,
        batch_id: str,
        source: str,
        source_batch_key: str,
        files: List[WorkspaceSourceFile],
        graph_mode: str = "hybrid",
        workspace_id: str | None = None,
    ) -> WorkspaceBuildResult:
        if not files:
            raise ValueError("At least one normalized file is required to prepare a GraphRAG workspace")

        tenant_key = _safe_segment(tenant_id, "default")
        batch_key = _safe_segment(batch_id, "batch")
        workspace_key = _safe_segment(workspace_id or str(uuid.uuid4()), "workspace")
        workspace_dir = (self.runtime.workspaces_root / tenant_key / batch_key / workspace_key).resolve()
        input_dir = workspace_dir / self.runtime.input_dir
        prompt_dir = workspace_dir / "prompts"
        cache_dir = workspace_dir / self.runtime.cache_dir
        output_dir = workspace_dir / "output"

        for path in (workspace_dir, input_dir, prompt_dir, cache_dir, output_dir):
            path.mkdir(parents=True, exist_ok=True)

        prompt_targets = self.prompt_registry.materialize(prompt_dir)

        manifest_files: List[Dict[str, Any]] = []
        for index, item in enumerate(files, start=1):
            text_content = str(item.text_content or "").strip()
            if not text_content:
                raise ValueError(f"Normalized text is empty for {item.file_name}")

            normalized_name = f"{index:03d}_{_safe_file_stem(item.file_name)}_hash-{item.file_hash[:7]}.txt"
            target_path = input_dir / normalized_name
            target_path.write_text(f"{text_content}\n", encoding="utf-8")

            manifest_files.append(
                {
                    "file_name": item.file_name,
                    "file_hash": item.file_hash,
                    "source_kind": item.source_kind,
                    "input_txt": str(target_path),
                    "original_path": item.original_path,
                    "artifact_path": item.artifact_path,
                    "artifact_url": item.artifact_url,
                    "text_length": len(text_content),
                    "normalization_status": "success",
                    "error": "",
                    "metadata": dict(item.metadata or {}),
                }
            )

        env_path = workspace_dir / ".env"
        env_path.write_text(render_workspace_env(self.runtime, self.neo4j, prompt_targets), encoding="utf-8")

        settings_path = workspace_dir / "settings.yaml"
        settings_path.write_text(render_settings_yaml(self.runtime, prompt_targets), encoding="utf-8")

        log_path = workspace_dir / "graphrag-index.log"
        log_path.touch(exist_ok=True)

        manifest_path = workspace_dir / "workspace_manifest.json"
        manifest_payload = {
            "tenant_id": tenant_key,
            "batch_id": batch_key,
            "workspace_id": workspace_key,
            "workspace_dir": str(workspace_dir),
            "source": source,
            "source_batch_key": source_batch_key,
            "created_at": _now_utc_iso(),
            "graph_mode": graph_mode,
            "files": manifest_files,
            "prompt_assets": {key: str(path) for key, path in prompt_targets.items()},
            "status": "prepared",
            "last_error": "" if self.runtime.is_configured() else "OneAPI runtime is not configured",
            "last_index_status": "pending",
            "latest_output_dir": None,
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return WorkspaceBuildResult(
            tenant_id=tenant_key,
            batch_id=batch_key,
            workspace_id=workspace_key,
            workspace_dir=workspace_dir,
            env_path=env_path,
            settings_path=settings_path,
            manifest_path=manifest_path,
            input_dir=input_dir,
            prompt_dir=prompt_dir,
            files=manifest_files,
        )
