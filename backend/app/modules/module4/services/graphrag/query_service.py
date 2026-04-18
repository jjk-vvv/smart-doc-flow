from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Dict, Iterable, Literal, Optional

from .prompts import PromptRegistry
from .query_adapter import load_artifact_graph_snapshot

if TYPE_CHECKING:
    import pandas as pd


GraphRAGQueryMode = Literal["local", "global", "drift", "basic"]


@dataclass(frozen=True)
class GraphRAGResolvedRuntime:
    graph_file: Dict[str, Any]
    graph_version: Dict[str, Any]
    workspace_dir: Path
    artifacts_dir: Path


class GraphRAGQueryServiceError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _apply_query_prompt_paths(config: Any) -> None:
    """Force query prompts to use the latest module4 prompt assets.

    Existing workspaces may contain stale prompt snapshots. Query runtime should always
    resolve to the latest canonical prompt files under
    backend/app/modules/module4/assets/prompts.
    """

    try:
        registry = PromptRegistry()
    except Exception:
        return

    def _prompt_path(key: str) -> str | None:
        try:
            path = registry.prompt_path(key).resolve()
        except Exception:
            return None
        return str(path) if path.exists() else None

    local_prompt = _prompt_path("local_search_system_prompt")
    global_map_prompt = _prompt_path("global_search_map_system_prompt")
    global_reduce_prompt = _prompt_path("global_search_reduce_system_prompt")
    global_knowledge_prompt = _prompt_path("global_search_knowledge_system_prompt")
    drift_prompt = _prompt_path("drift_search_system_prompt")
    drift_reduce_prompt = _prompt_path("drift_reduce_prompt")
    basic_prompt = _prompt_path("basic_search_system_prompt")

    try:
        if local_prompt and getattr(config, "local_search", None) is not None:
            config.local_search.prompt = local_prompt
        if global_map_prompt and getattr(config, "global_search", None) is not None:
            config.global_search.map_prompt = global_map_prompt
        if global_reduce_prompt and getattr(config, "global_search", None) is not None:
            config.global_search.reduce_prompt = global_reduce_prompt
        if global_knowledge_prompt and getattr(config, "global_search", None) is not None:
            config.global_search.knowledge_prompt = global_knowledge_prompt
        if drift_prompt and getattr(config, "drift_search", None) is not None:
            config.drift_search.prompt = drift_prompt
        if drift_reduce_prompt and getattr(config, "drift_search", None) is not None:
            config.drift_search.reduce_prompt = drift_reduce_prompt
        if basic_prompt and getattr(config, "basic_search", None) is not None:
            config.basic_search.prompt = basic_prompt
    except Exception:
        # Do not fail query execution if a prompt override cannot be applied.
        return


def _ensure_template_safe_settings(workspace_dir: Path) -> None:
    """Escape non-placeholder '$' symbols in settings.yaml for Template substitution.

    GraphRAG config loader performs ``string.Template.substitute`` over the whole
    settings file. Unescaped regex anchors like ``$`` in file patterns can trigger
    ``Invalid placeholder in string``.
    """

    settings_path = workspace_dir / "settings.yaml"
    if not settings_path.exists():
        return

    try:
        text = settings_path.read_text(encoding="utf-8")
    except Exception:
        return

    # Canonicalize regex anchors in file_pattern to avoid string.Template parsing errors.
    # Example:
    #   file_pattern: ".*\\.txt$"   -> file_pattern: ".*\\.txt$$"
    #   file_pattern: ".*\\.txt$$$" -> file_pattern: ".*\\.txt$$"
    patched = re.sub(r'(\.txt)\$+\\?"', r'\1$$"', text)
    if patched == text:
        return

    try:
        settings_path.write_text(patched, encoding="utf-8")
    except Exception:
        return


def _ensure_query_env_defaults(*, runtime: GraphRAGResolvedRuntime | None = None) -> None:
    # GraphRAG settings templates can reference ${timestamp}. Bind the query runtime
    # to the active output snapshot to avoid drifting to an empty "query-runtime" path.
    if runtime is not None:
        snapshot_name = str(runtime.artifacts_dir.parent.name or "").strip()
        if snapshot_name:
            os.environ["timestamp"] = snapshot_name


def _query_storage_cli_overrides(runtime: GraphRAGResolvedRuntime) -> Dict[str, Any]:
    output_dir = runtime.artifacts_dir.parent
    return {
        "output_storage": {
            "base_dir": str(runtime.artifacts_dir),
        },
        "update_output_storage": {
            "base_dir": str(runtime.artifacts_dir),
        },
        "reporting": {
            "base_dir": str(output_dir / "reports"),
        },
        # Query modes local/basic/drift depend on vector stores. We must always
        # point to the active output snapshot rather than a synthetic timestamp.
        "vector_store": {
            "db_uri": str(output_dir / "lancedb"),
        },
    }


def _query_model_cli_overrides() -> Dict[str, Any]:
    api_base = str(os.getenv("MODULE4_GRAPHRAG_API_BASE") or os.getenv("GRAPHRAG_API_BASE") or "").strip()
    chat_model = str(
        os.getenv("MODULE4_GRAPHRAG_CHAT_MODEL") or os.getenv("GRAPHRAG_CHAT_MODEL") or "gpt-4.1-mini"
    ).strip()
    chat_api_key = str(
        os.getenv("MODULE4_GRAPHRAG_CHAT_API_KEY") or os.getenv("GRAPHRAG_CHAT_API_KEY") or ""
    ).strip()
    embedding_model = str(
        os.getenv("MODULE4_GRAPHRAG_EMBEDDING_MODEL")
        or os.getenv("GRAPHRAG_EMBEDDING_MODEL")
        or "text-embedding-3-small"
    ).strip()
    embedding_api_key = str(
        os.getenv("MODULE4_GRAPHRAG_EMBEDDING_API_KEY") or os.getenv("GRAPHRAG_EMBEDDING_API_KEY") or ""
    ).strip()

    completion_config: Dict[str, Any] = {
        "type": "litellm",
        "model_provider": "openai",
        "model": chat_model,
    }
    if api_base:
        completion_config["api_base"] = api_base
    if chat_api_key:
        completion_config["api_key"] = chat_api_key

    embedding_config: Dict[str, Any] = {
        "type": "litellm",
        "model_provider": "openai",
        "model": embedding_model,
    }
    if api_base:
        embedding_config["api_base"] = api_base
    if embedding_api_key:
        embedding_config["api_key"] = embedding_api_key

    return {
        "completion_models": {
            "default_completion_model": completion_config,
        },
        "embedding_models": {
            "default_embedding_model": embedding_config,
        },
    }


def _float_env(name: str) -> float | None:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _query_timeout_seconds(mode: GraphRAGQueryMode) -> float | None:
    mode_key = str(mode or "").strip().upper()
    specific = _float_env(f"MODULE4_GRAPHRAG_QUERY_TIMEOUT_{mode_key}_SEC")
    if specific is not None:
        return specific

    shared = _float_env("MODULE4_GRAPHRAG_QUERY_TIMEOUT_SEC")
    if shared is not None:
        return shared

    defaults: Dict[str, float] = {
        "BASIC": 120.0,
        "LOCAL": 120.0,
        "GLOBAL": 180.0,
        "DRIFT": 90.0,
    }
    return defaults.get(mode_key)


def _query_subprocess_timeout_seconds(mode: GraphRAGQueryMode) -> float:
    configured = _float_env("MODULE4_GRAPHRAG_QUERY_SUBPROCESS_TIMEOUT_SEC")
    if configured is not None and configured > 0:
        return max(1.0, configured)
    fallback = _query_timeout_seconds(mode)
    if fallback is not None and fallback > 0:
        return max(60.0, fallback + 30.0)
    return 180.0


def _runtime_root_dir() -> Path:
    configured_root = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT") or "").strip()
    if configured_root:
        return Path(configured_root).resolve()
    return Path(__file__).resolve().parents[6]


def _backend_root_dir() -> Path:
    return (_runtime_root_dir() / "backend").resolve()


def _resolve_query_python_bin() -> str:
    configured = str(
        os.getenv("MODULE4_GRAPHRAG_QUERY_PYTHON_BIN")
        or os.getenv("MODULE4_GRAPHRAG_PYTHON_BIN")
        or ""
    ).strip()
    generic_commands = {"python", "python3", "py"}
    if configured and configured.lower() not in generic_commands:
        return configured

    runtime_root = _runtime_root_dir()
    candidates = [
        runtime_root / ".venv-module4-py311" / "Scripts" / "python.exe",
        runtime_root / ".venv-module4-py311" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return str(candidate)

    if configured:
        return configured
    return sys.executable


async def _run_query_with_timeout(
    *,
    mode: GraphRAGQueryMode,
    coro: Awaitable[tuple[Any, Any]],
) -> tuple[Any, Any]:
    timeout_seconds = _query_timeout_seconds(mode)
    if timeout_seconds is None or timeout_seconds <= 0:
        return await coro

    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise GraphRAGQueryServiceError(
            f"GraphRAG {mode} query timed out after {timeout_seconds:.1f}s.",
            status_code=504,
        ) from exc


def _ensure_query_artifact_aliases(artifacts_dir: Path) -> None:
    """Create query-time parquet aliases expected by GraphRAG DataReader."""

    alias_candidates: Dict[str, tuple[str, ...]] = {
        "entities": ("create_final_entities.parquet", "entities.parquet"),
        "communities": ("create_final_communities.parquet", "communities.parquet"),
        "community_reports": ("create_final_community_reports.parquet", "community_reports.parquet"),
        "text_units": ("create_final_text_units.parquet", "create_base_text_units.parquet", "text_units.parquet"),
        "relationships": ("create_final_relationships.parquet", "relationships.parquet"),
        "covariates": ("create_final_covariates.parquet", "covariates.parquet"),
        "documents": ("create_final_documents.parquet", "documents.parquet"),
    }

    for alias_name, candidates in alias_candidates.items():
        target = artifacts_dir / f"{alias_name}.parquet"
        if target.exists():
            if alias_name != "text_units":
                continue
            try:
                import pyarrow.parquet as pq

                existing = pq.read_table(target)
                if "text" in existing.column_names and "document_id" in existing.column_names:
                    continue
                target.unlink(missing_ok=True)
            except Exception:
                continue
        source: Path | None = None
        for candidate in candidates:
            path = artifacts_dir / candidate
            if path.exists():
                source = path
                break
        if source is None:
            continue

        if alias_name == "text_units":
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq

                table = pq.read_table(source)
                frame = table.to_pandas()
                if "text" not in frame.columns and "chunk" in frame.columns:
                    frame["text"] = frame["chunk"]
                if "text" not in frame.columns:
                    frame["text"] = frame.get("raw_content", "")
                if "document_id" not in frame.columns and "document_ids" in frame.columns:
                    frame["document_id"] = frame["document_ids"].apply(
                        lambda value: (
                            value[0]
                            if isinstance(value, list) and value
                            else (value if isinstance(value, str) else "")
                        )
                    )
                if "document_id" not in frame.columns and "doc_id" in frame.columns:
                    frame["document_id"] = frame["doc_id"]
                if "document_id" not in frame.columns:
                    frame["document_id"] = ""
                table = pa.Table.from_pandas(frame, preserve_index=False)
                pq.write_table(table, target)
                continue
            except Exception:
                pass

        try:
            os.link(source, target)
        except Exception:
            try:
                shutil.copyfile(source, target)
            except Exception:
                continue


def _ensure_dir(path_value: Any, *, label: str) -> Path:
    target = Path(str(path_value or "").strip()).resolve()
    if not str(path_value or "").strip():
        raise GraphRAGQueryServiceError(f"{label} is missing for the active GraphRAG version.")
    if not target.exists() or not target.is_dir():
        raise GraphRAGQueryServiceError(f"{label} does not exist: {target}")
    return target


def _resolve_workspace_dir(graph_file: Dict[str, Any], graph_version: Dict[str, Any]) -> Path:
    metadata = _as_dict(graph_file.get("metadata"))
    candidates: list[Path] = []

    workspace_dir_value = str(metadata.get("workspace_dir") or "").strip()
    if workspace_dir_value:
        candidates.append(Path(workspace_dir_value))

    manifest_path_value = str(graph_version.get("manifest_path") or "").strip()
    if manifest_path_value:
        candidates.append(Path(manifest_path_value).resolve().parent)

    for key in ("output_dir", "artifacts_dir", "reports_dir"):
        raw = str(graph_version.get(key) or "").strip()
        if not raw:
            continue
        current = Path(raw).resolve()
        candidates.extend([current, *list(current.parents[:4])])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "settings.yaml").exists():
            return resolved

    raise GraphRAGQueryServiceError(
        "Unable to resolve the GraphRAG workspace for the active graph version.",
    )


async def _resolve_runtime(
    *,
    storage: Any,
    tenant_id: str,
    file_hash: str,
) -> GraphRAGResolvedRuntime:
    graph_file = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not graph_file:
        raise GraphRAGQueryServiceError("Graph file not found.", status_code=404)

    active_version_id = str(graph_file.get("active_version_id") or "").strip()
    if not active_version_id:
        raise GraphRAGQueryServiceError(
            "This graph file does not have an active GraphRAG version yet. Please rebuild or re-index it first."
        )

    graph_version = await storage.get_graph_version(
        tenant_id=tenant_id,
        graph_version_id=active_version_id,
    )
    if not graph_version:
        raise GraphRAGQueryServiceError("The active GraphRAG version record could not be found.")

    artifacts_dir = _ensure_dir(graph_version.get("artifacts_dir"), label="GraphRAG artifacts directory")
    workspace_dir = _resolve_workspace_dir(graph_file, graph_version)
    return GraphRAGResolvedRuntime(
        graph_file=graph_file,
        graph_version=graph_version,
        workspace_dir=workspace_dir,
        artifacts_dir=artifacts_dir,
    )


async def _load_output_frames(
    *,
    runtime: GraphRAGResolvedRuntime,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> tuple[Any, Dict[str, "pd.DataFrame | None"]]:
    try:
        from graphrag.config.load_config import load_config
        from graphrag_storage import create_storage
        from graphrag_storage.tables.table_provider_factory import create_table_provider
        from graphrag.data_model.data_reader import DataReader
    except ModuleNotFoundError as exc:
        raise GraphRAGQueryServiceError(
            "The GraphRAG query runtime is not installed in the current Python environment."
        ) from exc

    _ensure_query_artifact_aliases(runtime.artifacts_dir)

    cli_overrides: Dict[str, Any] = _query_storage_cli_overrides(runtime)
    cli_overrides.update(_query_model_cli_overrides())
    _ensure_template_safe_settings(runtime.workspace_dir)
    _ensure_query_env_defaults(runtime=runtime)
    config = load_config(root_dir=runtime.workspace_dir, cli_overrides=cli_overrides)
    _apply_query_prompt_paths(config)
    storage_obj = create_storage(config.output_storage)
    table_provider = create_table_provider(config.table_provider, storage=storage_obj)
    reader = DataReader(table_provider)

    frames: Dict[str, "pd.DataFrame | None"] = {}
    for name in required:
        try:
            frames[name] = await getattr(reader, name)()
        except AttributeError as exc:
            raise GraphRAGQueryServiceError(f"Unsupported GraphRAG artifact reader: {name}") from exc
        except Exception as exc:
            raise GraphRAGQueryServiceError(
                f"Failed to read required GraphRAG artifact '{name}' from {runtime.artifacts_dir}: {exc}"
            ) from exc

    for name in optional:
        try:
            has_file = await table_provider.has(name)
        except Exception:
            has_file = False
        if not has_file:
            frames[name] = None
            continue
        try:
            frames[name] = await getattr(reader, name)()
        except AttributeError as exc:
            raise GraphRAGQueryServiceError(f"Unsupported GraphRAG artifact reader: {name}") from exc
        except Exception as exc:
            raise GraphRAGQueryServiceError(
                f"Failed to read optional GraphRAG artifact '{name}' from {runtime.artifacts_dir}: {exc}"
            ) from exc

    return config, frames


def _append_linked_node_id(candidates: list[str], seen: set[str], prefix: str, raw_value: Any) -> None:
    value = str(raw_value or "").strip()
    if not value:
        return
    node_id = value if "::" in value else f"{prefix}::{value}"
    if node_id in seen:
        return
    seen.add(node_id)
    candidates.append(node_id)


def _linked_node_ids_from_context(context_data: Dict[str, list[Dict[str, Any]]]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for row in context_data.get("entities", []):
        _append_linked_node_id(candidates, seen, "entity", row.get("id"))

    for row in context_data.get("reports", []):
        _append_linked_node_id(
            candidates,
            seen,
            "community_report",
            row.get("id") or row.get("report_id") or row.get("human_readable_id"),
        )
        _append_linked_node_id(candidates, seen, "community", row.get("community") or row.get("community_id"))

    for row in context_data.get("sources", []):
        _append_linked_node_id(candidates, seen, "chunk", row.get("id"))
        for key in ("document_ids", "document_id"):
            value = row.get(key)
            if isinstance(value, list):
                for document_id in value:
                    _append_linked_node_id(candidates, seen, "doc", document_id)
            else:
                _append_linked_node_id(candidates, seen, "doc", value)

    for row in context_data.get("claims", []):
        _append_linked_node_id(candidates, seen, "covariate", row.get("id"))

    return candidates


def _dedupe_non_empty(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _append_alias(alias_map: Dict[str, str], alias_value: Any, node_id: str, *, prefix: str = "") -> None:
    alias_text = str(alias_value or "").strip()
    if not alias_text:
        return
    variants = [alias_text]
    if prefix and "::" not in alias_text:
        variants.append(f"{prefix}::{alias_text}")
    for variant in variants:
        key = str(variant or "").strip()
        if not key:
            continue
        if key not in alias_map:
            alias_map[key] = node_id
        lower_key = key.lower()
        if lower_key not in alias_map:
            alias_map[lower_key] = node_id


def _linked_node_alias_map_for_graph_file(graph_file: Dict[str, Any]) -> Dict[str, str]:
    artifact_graph = load_artifact_graph_snapshot(graph_file)
    if artifact_graph is None:
        return {}

    alias_map: Dict[str, str] = {}
    alias_attr_keys = (
        "graphrag_id",
        "human_readable_id",
        "report_id",
        "id",
        "name",
        "title",
        "community",
        "community_id",
    )
    for node in artifact_graph.nodes:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            continue
        prefix, _, suffix = node_id.partition("::")
        _append_alias(alias_map, node_id, node_id)
        _append_alias(alias_map, suffix, node_id, prefix=prefix)
        _append_alias(alias_map, node.get("canonical_key"), node_id, prefix=prefix)
        _append_alias(alias_map, node.get("display_name"), node_id, prefix=prefix)

        attrs_raw = node.get("attrs")
        attrs = attrs_raw if isinstance(attrs_raw, dict) else {}
        for key in alias_attr_keys:
            value = attrs.get(key)
            if isinstance(value, list):
                for item in value:
                    _append_alias(alias_map, item, node_id, prefix=prefix)
            else:
                _append_alias(alias_map, value, node_id, prefix=prefix)

    return alias_map


def _canonicalize_linked_node_ids(
    *,
    candidates: Iterable[Any],
    graph_file: Dict[str, Any],
) -> list[str]:
    deduped_candidates = _dedupe_non_empty(candidates)
    if not deduped_candidates:
        return []

    alias_map = _linked_node_alias_map_for_graph_file(graph_file)
    if not alias_map:
        return deduped_candidates

    resolved: list[str] = []
    seen: set[str] = set()
    for candidate in deduped_candidates:
        mapped = alias_map.get(candidate) or alias_map.get(candidate.lower())
        if not mapped and "::" in candidate:
            _, _, suffix = candidate.partition("::")
            mapped = alias_map.get(suffix) or alias_map.get(suffix.lower())
        if not mapped:
            continue
        if mapped in seen:
            continue
        seen.add(mapped)
        resolved.append(mapped)

    # linked_node_ids is used for graph highlight. Prefer only canonical node ids.
    # If none can be resolved (unexpected runtime mismatch), preserve original ids.
    return resolved or deduped_candidates


async def _linked_node_alias_map_for_graph_file_from_storage(
    *,
    storage: Any,
    tenant_id: str,
    graph_file: Dict[str, Any],
) -> Dict[str, str]:
    list_nodes_by_graph_file = getattr(storage, "list_nodes_by_graph_file", None)
    if not callable(list_nodes_by_graph_file):
        return {}

    graph_file_id = str(graph_file.get("graph_file_id") or "").strip()
    if not graph_file_id:
        return {}

    try:
        rows = await list_nodes_by_graph_file(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            node_types=[],
            limit=12000,
        )
    except Exception:
        return {}

    alias_map: Dict[str, str] = {}
    alias_attr_keys = (
        "graphrag_id",
        "human_readable_id",
        "report_id",
        "id",
        "name",
        "title",
        "community",
        "community_id",
    )
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or "").strip()
        if not node_id:
            continue
        prefix, _, suffix = node_id.partition("::")
        _append_alias(alias_map, node_id, node_id)
        _append_alias(alias_map, suffix, node_id, prefix=prefix)
        _append_alias(alias_map, row.get("canonical_key"), node_id, prefix=prefix)
        _append_alias(alias_map, row.get("display_name"), node_id, prefix=prefix)
        attrs_raw = row.get("attrs")
        attrs = attrs_raw if isinstance(attrs_raw, dict) else {}
        for key in alias_attr_keys:
            value = attrs.get(key)
            if isinstance(value, list):
                for item in value:
                    _append_alias(alias_map, item, node_id, prefix=prefix)
            else:
                _append_alias(alias_map, value, node_id, prefix=prefix)
    return alias_map


async def _canonicalize_linked_node_ids_with_storage(
    *,
    candidates: Iterable[Any],
    graph_file: Dict[str, Any],
    storage: Any,
    tenant_id: str,
) -> list[str]:
    linked_node_ids, _ = await _canonicalize_linked_node_ids_with_storage_diagnostics(
        candidates=candidates,
        graph_file=graph_file,
        storage=storage,
        tenant_id=tenant_id,
    )
    return linked_node_ids


def _resolve_candidate_from_alias_map(candidate: str, alias_map: Dict[str, str]) -> str | None:
    if not alias_map:
        return None
    mapped = alias_map.get(candidate) or alias_map.get(candidate.lower())
    if mapped:
        return mapped
    if "::" in candidate:
        _, _, suffix = candidate.partition("::")
        mapped = alias_map.get(suffix) or alias_map.get(suffix.lower())
    return mapped


def _resolution_strategy_label(*, storage_alias_count: int, artifact_alias_count: int) -> str:
    if storage_alias_count > 0 and artifact_alias_count > 0:
        return "artifact_first_then_storage"
    if storage_alias_count > 0:
        return "storage_only"
    if artifact_alias_count > 0:
        return "artifact_only"
    return "identity_fallback"


def _known_graph_node_ids(*alias_maps: Dict[str, str]) -> set[str]:
    node_ids: set[str] = set()
    for alias_map in alias_maps:
        for mapped in alias_map.values():
            node_id = str(mapped or "").strip()
            if node_id:
                node_ids.add(node_id)
    return node_ids


async def _canonicalize_linked_node_ids_with_storage_diagnostics(
    *,
    candidates: Iterable[Any],
    graph_file: Dict[str, Any],
    storage: Any,
    tenant_id: str,
) -> tuple[list[str], Dict[str, Any]]:
    deduped_candidates = _dedupe_non_empty(candidates)
    if not deduped_candidates:
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "storage_alias_count": 0,
            "artifact_alias_count": 0,
            "resolution_strategy": "identity_fallback",
            "used_fallback_candidates": False,
        }

    storage_alias_map = await _linked_node_alias_map_for_graph_file_from_storage(
        storage=storage,
        tenant_id=tenant_id,
        graph_file=graph_file,
    )
    artifact_alias_map = _linked_node_alias_map_for_graph_file(graph_file)

    resolved: list[str] = []
    seen: set[str] = set()
    unresolved: list[str] = []
    known_artifact_node_ids = _known_graph_node_ids(artifact_alias_map)
    known_storage_node_ids = _known_graph_node_ids(storage_alias_map)
    artifact_only_resolution = bool(known_artifact_node_ids)
    resolution_source_counts = {
        "storage": 0,
        "artifact": 0,
    }
    for candidate in deduped_candidates:
        mapped = _resolve_candidate_from_alias_map(candidate, artifact_alias_map) if artifact_only_resolution else None
        source = "artifact" if artifact_only_resolution else "storage"
        if not mapped and not artifact_only_resolution:
            mapped = _resolve_candidate_from_alias_map(candidate, storage_alias_map)
            source = "storage"

        if not mapped:
            unresolved.append(candidate)
            continue

        resolution_source_counts[source] += 1
        if mapped not in seen:
            seen.add(mapped)
            resolved.append(mapped)

    linked_node_ids = list(resolved)
    fallback_known_node_ids = known_artifact_node_ids or known_storage_node_ids
    if not linked_node_ids and fallback_known_node_ids:
        for candidate in deduped_candidates:
            normalized_candidate = str(candidate or "").strip()
            if not normalized_candidate or normalized_candidate not in fallback_known_node_ids:
                continue
            if normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)
            linked_node_ids.append(normalized_candidate)

    used_fallback_candidates = bool(linked_node_ids) and not bool(resolved)
    unresolved_for_report = [candidate for candidate in deduped_candidates if candidate not in set(linked_node_ids)]
    if not unresolved_for_report and unresolved:
        unresolved_for_report = unresolved
    diagnostics = {
        "candidate_count": len(deduped_candidates),
        "resolved_count": len(resolved),
        "linked_node_id_count": len(linked_node_ids),
        "unresolved_count": len(unresolved_for_report),
        "unresolved_candidates": unresolved_for_report[:20],
        "storage_alias_count": len(storage_alias_map),
        "artifact_alias_count": len(artifact_alias_map),
        "resolution_strategy": _resolution_strategy_label(
            storage_alias_count=len(storage_alias_map),
            artifact_alias_count=len(artifact_alias_map),
        ),
        "resolution_source_counts": resolution_source_counts,
        "used_fallback_candidates": used_fallback_candidates,
    }
    return linked_node_ids, diagnostics


def _serialize_answer(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _fallback_basic_search_from_text_units(
    text_units: Any,
    *,
    query: str,
    reason: str | None = None,
    max_items: int = 5,
) -> tuple[str, Dict[str, list[Dict[str, Any]]]]:
    """Fallback retrieval when GraphRAG basic_search runtime is unavailable."""

    records: list[Dict[str, Any]] = []
    if text_units is None:
        text_units = []

    try:
        records = text_units.to_dict(orient="records")  # type: ignore[assignment]
    except Exception:
        try:
            records = list(text_units)
        except Exception:
            records = []

    query_text = str(query or "").strip()
    terms = [term for term in re.split(r"[\s,，。；;、]+", query_text) if term] or ([query_text] if query_text else [])

    def _row_text(row: Dict[str, Any]) -> str:
        for key in ("text", "chunk", "raw_content", "content"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    ranked: list[tuple[int, Dict[str, Any], str]] = []
    for row in records:
        text = _row_text(row)
        if not text:
            continue
        score = 0
        if terms:
            for term in terms:
                if term and term in text:
                    score += 1
        else:
            score = 1
        if score == 0:
            continue
        ranked.append((score, row, text))

    if not ranked:
        ranked = [(1, row, _row_text(row)) for row in records if _row_text(row)]

    ranked.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    top_rows = ranked[: max(1, max_items)]

    sources: list[Dict[str, Any]] = []
    bullets: list[str] = []
    for idx, (_, row, text) in enumerate(top_rows, start=1):
        source_id = str(row.get("id") or row.get("chunk_id") or f"text_unit_{idx}")
        document_id = row.get("document_id")
        if not document_id:
            doc_ids = row.get("document_ids")
            if isinstance(doc_ids, list) and doc_ids:
                document_id = doc_ids[0]
            elif isinstance(doc_ids, str):
                document_id = doc_ids
        preview = text.strip().replace("\n", " ")
        if len(preview) > 180:
            preview = f"{preview[:177].rstrip()}..."
        bullets.append(f"{idx}. {preview}")
        sources.append(
            {
                "id": source_id,
                "text": text,
                "document_id": str(document_id or ""),
            }
        )

    reason_text = str(reason or "").strip()
    answer = (
        "当前索引暂时无法完成完整 GraphRAG 查询，已自动切换为文本片段检索兜底模式。\n\n"
        f"问题：{query_text or '未提供问题'}\n\n"
        + (f"降级原因：{reason_text}\n\n" if reason_text else "")
        + "相关片段：\n"
        + "\n".join(bullets)
    )
    return answer, {
        "reports": [],
        "entities": [],
        "relationships": [],
        "claims": [],
        "sources": sources,
    }


async def _execute_query_runtime(
    *,
    runtime: GraphRAGResolvedRuntime,
    mode_value: GraphRAGQueryMode,
    query_text: str,
    response_type_value: str,
    community_level_value: Optional[int],
    dynamic_community_selection: bool,
    verbose: bool,
    graphrag_api: Any,
    reformat_context_data: Any,
) -> Dict[str, Any]:
    effective_mode_value = mode_value
    try:
        try:
            if mode_value == "global":
                config, frames = await _load_output_frames(
                    runtime=runtime,
                    required=("entities", "communities", "community_reports"),
                )
                answer, context_data = await _run_query_with_timeout(
                    mode="global",
                    coro=graphrag_api.global_search(
                        config=config,
                        entities=frames["entities"],
                        communities=frames["communities"],
                        community_reports=frames["community_reports"],
                        community_level=community_level_value,
                        dynamic_community_selection=bool(dynamic_community_selection),
                        response_type=response_type_value,
                        query=query_text,
                        verbose=verbose,
                    ),
                )
            elif mode_value == "drift":
                config, frames = await _load_output_frames(
                    runtime=runtime,
                    required=("entities", "communities", "community_reports", "text_units", "relationships"),
                )
                answer, context_data = await _run_query_with_timeout(
                    mode="drift",
                    coro=graphrag_api.drift_search(
                        config=config,
                        entities=frames["entities"],
                        communities=frames["communities"],
                        community_reports=frames["community_reports"],
                        text_units=frames["text_units"],
                        relationships=frames["relationships"],
                        community_level=2 if community_level_value is None else community_level_value,
                        response_type=response_type_value,
                        query=query_text,
                        verbose=verbose,
                    ),
                )
            elif mode_value == "basic":
                config, frames = await _load_output_frames(
                    runtime=runtime,
                    required=("text_units",),
                )
                answer, context_data = await _run_query_with_timeout(
                    mode="basic",
                    coro=graphrag_api.basic_search(
                        config=config,
                        text_units=frames["text_units"],
                        response_type=response_type_value,
                        query=query_text,
                        verbose=verbose,
                    ),
                )
            else:
                config, frames = await _load_output_frames(
                    runtime=runtime,
                    required=("entities", "communities", "community_reports", "text_units", "relationships"),
                    optional=("covariates",),
                )
                answer, context_data = await _run_query_with_timeout(
                    mode="local",
                    coro=graphrag_api.local_search(
                        config=config,
                        entities=frames["entities"],
                        communities=frames["communities"],
                        community_reports=frames["community_reports"],
                        text_units=frames["text_units"],
                        relationships=frames["relationships"],
                        covariates=frames.get("covariates"),
                        community_level=2 if community_level_value is None else community_level_value,
                        response_type=response_type_value,
                        query=query_text,
                        verbose=verbose,
                    ),
                )
        except GraphRAGQueryServiceError as exc:
            detail_text = str(exc.detail or "")
            detail_lower = detail_text.lower()
            timeout_error = exc.status_code == 504 or "timeout" in detail_lower or "timed out" in detail_lower
            needs_fallback = mode_value != "basic" and (
                "Failed to read required GraphRAG artifact" in detail_text or timeout_error
            )
            if not needs_fallback:
                raise

            fallback_reason = detail_text
            use_basic_fallback = True

            if mode_value == "drift":
                try:
                    local_config, local_frames = await _load_output_frames(
                        runtime=runtime,
                        required=("entities", "communities", "community_reports", "text_units", "relationships"),
                        optional=("covariates",),
                    )
                    answer, context_data = await _run_query_with_timeout(
                        mode="local",
                        coro=graphrag_api.local_search(
                            config=local_config,
                            entities=local_frames["entities"],
                            communities=local_frames["communities"],
                            community_reports=local_frames["community_reports"],
                            text_units=local_frames["text_units"],
                            relationships=local_frames["relationships"],
                            covariates=local_frames.get("covariates"),
                            community_level=2 if community_level_value is None else community_level_value,
                            response_type=response_type_value,
                            query=query_text,
                            verbose=verbose,
                        ),
                    )
                    effective_mode_value = "local"
                    use_basic_fallback = False
                except Exception as local_exc:
                    fallback_reason = (
                        f"{detail_text}; drift->local fallback failed: "
                        f"{type(local_exc).__name__}: {local_exc}"
                    )

            if use_basic_fallback:
                config, frames = await _load_output_frames(
                    runtime=runtime,
                    required=("text_units",),
                )
                try:
                    answer, context_data = await _run_query_with_timeout(
                        mode="basic",
                        coro=graphrag_api.basic_search(
                            config=config,
                            text_units=frames["text_units"],
                            response_type=response_type_value,
                            query=query_text,
                            verbose=verbose,
                        ),
                    )
                except Exception:
                    answer, context_data = _fallback_basic_search_from_text_units(
                        frames.get("text_units"),
                        query=query_text,
                        reason=fallback_reason,
                    )
                effective_mode_value = "basic"
    except GraphRAGQueryServiceError:
        raise
    except Exception as exc:
        try:
            config, frames = await _load_output_frames(
                runtime=runtime,
                required=("text_units",),
            )
            try:
                answer, context_data = await _run_query_with_timeout(
                    mode="basic",
                    coro=graphrag_api.basic_search(
                        config=config,
                        text_units=frames["text_units"],
                        response_type=response_type_value,
                        query=query_text,
                        verbose=verbose,
                    ),
                )
            except Exception as basic_exc:
                answer, context_data = _fallback_basic_search_from_text_units(
                    frames.get("text_units"),
                    query=query_text,
                    reason=f"{type(exc).__name__}: {exc}; basic fallback: {type(basic_exc).__name__}: {basic_exc}",
                )
            effective_mode_value = "basic"
        except GraphRAGQueryServiceError:
            raise
        except Exception as fallback_exc:
            raise GraphRAGQueryServiceError(
                f"GraphRAG query execution failed: {exc}; fallback failed: {fallback_exc}"
            ) from fallback_exc

    raw_context = context_data if isinstance(context_data, dict) else {}
    if raw_context and all(isinstance(value, list) for value in raw_context.values()):
        normalized_context = {
            "reports": list(raw_context.get("reports", [])),
            "entities": list(raw_context.get("entities", [])),
            "relationships": list(raw_context.get("relationships", [])),
            "claims": list(raw_context.get("claims", [])),
            "sources": list(raw_context.get("sources", [])),
        }
    else:
        normalized_context = reformat_context_data(raw_context)

    return {
        "answer": _serialize_answer(answer),
        "mode": effective_mode_value,
        "context_data": normalized_context,
        "source": (
            f"graphrag:query:{mode_value}:fallback:{effective_mode_value}"
            if effective_mode_value != mode_value
            else f"graphrag:query:{mode_value}"
        ),
    }


def _subprocess_query_entry(raw_payload: str) -> Dict[str, Any]:
    try:
        payload = json.loads(str(raw_payload or "").strip() or "{}")
    except Exception as exc:
        raise RuntimeError(f"invalid subprocess query payload: {exc}") from exc

    workspace_dir = Path(str(payload.get("workspace_dir") or "").strip()).resolve()
    artifacts_dir = Path(str(payload.get("artifacts_dir") or "").strip()).resolve()
    runtime = GraphRAGResolvedRuntime(
        graph_file={},
        graph_version={},
        workspace_dir=workspace_dir,
        artifacts_dir=artifacts_dir,
    )
    mode_value = str(payload.get("mode") or "local").strip().lower()
    if mode_value not in {"local", "global", "drift", "basic"}:
        raise RuntimeError(f"unsupported mode in subprocess payload: {mode_value}")
    query_text = str(payload.get("query") or "").strip()
    if not query_text:
        raise RuntimeError("query cannot be empty in subprocess payload")
    response_type_value = str(payload.get("response_type") or "").strip() or "multiple paragraphs"
    community_level_value = payload.get("community_level")
    if community_level_value is not None:
        try:
            community_level_value = max(0, int(community_level_value))
        except Exception:
            community_level_value = None

    import graphrag.api as graphrag_api
    from graphrag.utils.api import reformat_context_data

    return asyncio.run(
        _execute_query_runtime(
            runtime=runtime,
            mode_value=mode_value,  # type: ignore[arg-type]
            query_text=query_text,
            response_type_value=response_type_value,
            community_level_value=community_level_value,
            dynamic_community_selection=bool(payload.get("dynamic_community_selection")),
            verbose=bool(payload.get("verbose")),
            graphrag_api=graphrag_api,
            reformat_context_data=reformat_context_data,
        )
    )


async def _execute_query_runtime_via_subprocess(
    *,
    runtime: GraphRAGResolvedRuntime,
    mode_value: GraphRAGQueryMode,
    query_text: str,
    response_type_value: str,
    community_level_value: Optional[int],
    dynamic_community_selection: bool,
    verbose: bool,
) -> Dict[str, Any]:
    python_bin = _resolve_query_python_bin()
    command = [
        python_bin,
        "-c",
        (
            "import json,sys;"
            "from app.modules.module4.services.graphrag.query_service import _subprocess_query_entry;"
            "result=_subprocess_query_entry(sys.stdin.read());"
            "sys.stdout.write(json.dumps(result, ensure_ascii=False))"
        ),
    ]
    payload = {
        "workspace_dir": str(runtime.workspace_dir),
        "artifacts_dir": str(runtime.artifacts_dir),
        "mode": str(mode_value),
        "query": query_text,
        "response_type": response_type_value,
        "community_level": community_level_value,
        "dynamic_community_selection": bool(dynamic_community_selection),
        "verbose": bool(verbose),
    }
    timeout_sec = _query_subprocess_timeout_seconds(mode_value)
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    def _run_subprocess() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            cwd=str(_backend_root_dir()),
            timeout=max(1.0, float(timeout_sec)),
            env=env,
        )

    try:
        completed = await asyncio.to_thread(_run_subprocess)
    except subprocess.TimeoutExpired as exc:
        raise GraphRAGQueryServiceError(
            f"GraphRAG subprocess query timed out after {float(timeout_sec):.1f}s.",
            status_code=504,
        ) from exc
    except FileNotFoundError as exc:
        raise GraphRAGQueryServiceError(
            f"GraphRAG query python runtime not found: {python_bin}",
            status_code=503,
        ) from exc
    except Exception as exc:
        raise GraphRAGQueryServiceError(
            f"GraphRAG subprocess query failed to start: {type(exc).__name__}: {exc}",
            status_code=503,
        ) from exc

    if completed.returncode != 0:
        stderr_text = str(completed.stderr or "").strip()
        stdout_text = str(completed.stdout or "").strip()
        detail = stderr_text or stdout_text or f"exit_code={completed.returncode}"
        raise GraphRAGQueryServiceError(
            f"GraphRAG subprocess query failed: {detail}",
            status_code=503,
        )

    output_text = str(completed.stdout or "").strip()
    if not output_text:
        raise GraphRAGQueryServiceError(
            "GraphRAG subprocess query returned an empty payload.",
            status_code=502,
        )
    try:
        payload_obj = json.loads(output_text)
    except Exception as exc:
        raise GraphRAGQueryServiceError(
            f"GraphRAG subprocess query returned invalid JSON: {exc}",
            status_code=502,
        ) from exc
    if not isinstance(payload_obj, dict):
        raise GraphRAGQueryServiceError(
            "GraphRAG subprocess query returned an unexpected payload.",
            status_code=502,
        )
    source_value = str(payload_obj.get("source") or "").strip()
    payload_obj["source"] = f"{source_value}:subprocess" if source_value else "graphrag:query:subprocess"
    return payload_obj


async def search_graph(
    *,
    storage: Any,
    tenant_id: str,
    file_hash: str,
    query: str,
    mode: GraphRAGQueryMode,
    response_type: str,
    community_level: Optional[int],
    dynamic_community_selection: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    runtime = await _resolve_runtime(storage=storage, tenant_id=tenant_id, file_hash=file_hash)
    mode_value = str(mode or "local").strip().lower()
    if mode_value not in {"local", "global", "drift", "basic"}:
        raise GraphRAGQueryServiceError(f"Unsupported GraphRAG query mode: {mode}", status_code=400)

    query_text = str(query or "").strip()
    if not query_text:
        raise GraphRAGQueryServiceError("Query text cannot be empty.", status_code=400)

    response_type_value = str(response_type or "").strip() or "multiple paragraphs"
    community_level_value = max(0, int(community_level or 0)) if community_level is not None else None
    query_runtime_payload: Dict[str, Any]
    try:
        import graphrag.api as graphrag_api
        from graphrag.utils.api import reformat_context_data
    except ModuleNotFoundError:
        query_runtime_payload = await _execute_query_runtime_via_subprocess(
            runtime=runtime,
            mode_value=mode_value,  # type: ignore[arg-type]
            query_text=query_text,
            response_type_value=response_type_value,
            community_level_value=community_level_value,
            dynamic_community_selection=bool(dynamic_community_selection),
            verbose=verbose,
        )
    else:
        query_runtime_payload = await _execute_query_runtime(
            runtime=runtime,
            mode_value=mode_value,  # type: ignore[arg-type]
            query_text=query_text,
            response_type_value=response_type_value,
            community_level_value=community_level_value,
            dynamic_community_selection=bool(dynamic_community_selection),
            verbose=verbose,
            graphrag_api=graphrag_api,
            reformat_context_data=reformat_context_data,
        )

    normalized_context_raw = query_runtime_payload.get("context_data")
    normalized_context = normalized_context_raw if isinstance(normalized_context_raw, dict) else {
        "reports": [],
        "entities": [],
        "relationships": [],
        "claims": [],
        "sources": [],
    }
    answer_value = _serialize_answer(query_runtime_payload.get("answer", ""))
    effective_mode_value = str(query_runtime_payload.get("mode") or mode_value).strip().lower() or mode_value
    source_value = str(query_runtime_payload.get("source") or "").strip()
    if not source_value:
        source_value = (
            f"graphrag:query:{mode_value}:fallback:{effective_mode_value}"
            if effective_mode_value != mode_value
            else f"graphrag:query:{mode_value}"
        )
    linked_node_candidates = _linked_node_ids_from_context(normalized_context)
    linked_node_ids, linked_node_resolution = await _canonicalize_linked_node_ids_with_storage_diagnostics(
        candidates=linked_node_candidates,
        graph_file=runtime.graph_file,
        storage=storage,
        tenant_id=tenant_id,
    )

    return {
        "answer": answer_value,
        "mode": effective_mode_value,
        "query": query_text,
        "response_type": response_type_value,
        "community_level": community_level_value,
        "dynamic_community_selection": bool(dynamic_community_selection),
        "file_hash": str(runtime.graph_file.get("file_hash") or file_hash),
        "graph_file_id": str(runtime.graph_file.get("graph_file_id") or "") or None,
        "active_version_id": str(runtime.graph_version.get("graph_version_id") or "") or None,
        "workspace_id": str(runtime.graph_file.get("workspace_id") or runtime.graph_version.get("workspace_id") or "")
        or None,
        "context_data": normalized_context,
        "linked_node_ids": linked_node_ids,
        "linked_node_resolution": linked_node_resolution,
        "source": source_value,
    }


