from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..query.neo4j import Neo4jSettings
from .settings import GraphRAGRuntimeSettings
from .prompts import PromptRegistry


def _module4_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    runtime_root = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if runtime_root:
        return Path(runtime_root).resolve()
    return _module4_root().parents[3]


def _repo_venv_python() -> Path:
    root = _repo_root()
    if os.name == "nt":
        return root / ".venv-module4-py311" / "Scripts" / "python.exe"
    return root / ".venv-module4-py311" / "bin" / "python"


def _resolve_python_bin() -> str:
    configured = str(os.getenv("MODULE4_GRAPHRAG_PYTHON_BIN", "") or "").strip()
    generic_commands = {"python", "python3", "py"}
    if configured and configured.lower() not in generic_commands:
        return configured

    repo_venv = _repo_venv_python()
    if repo_venv.exists():
        return str(repo_venv)

    if configured:
        return configured
    return sys.executable


def _workspace_env_file(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _augment_source_checkout_env(env: Dict[str, str], workspace_env: Dict[str, str]) -> Dict[str, str]:
    if not _truthy(workspace_env.get("GRAPHRAG_USE_SOURCE_CHECKOUT"), default=False):
        return env
    repo_root_text = str(workspace_env.get("GRAPHRAG_SOURCE_REPO_ROOT") or "").strip()
    if not repo_root_text:
        return env
    repo_root = Path(repo_root_text).resolve()
    packages_root = repo_root / "packages"
    if not packages_root.exists():
        return env

    package_names = (
        "graphrag",
        "graphrag-cache",
        "graphrag-chunking",
        "graphrag-common",
        "graphrag-input",
        "graphrag-llm",
        "graphrag-storage",
        "graphrag-vectors",
    )
    injected_paths: List[str] = []
    for package_name in package_names:
        package_path = (packages_root / package_name).resolve()
        if package_path.exists():
            injected_paths.append(str(package_path))

    if not injected_paths:
        return env
    existing = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = os.pathsep.join(injected_paths + ([existing] if existing else []))
    return env


def _truthy(value: str | None, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _retry_skip_community_reports_enabled(workspace_env: Dict[str, str]) -> bool:
    return _truthy(workspace_env.get("GRAPHRAG_RETRY_SKIP_COMMUNITY_REPORTS"), default=False)


def _runtime_style(workspace_env: Dict[str, str]) -> str:
    return str(workspace_env.get("GRAPHRAG_CONFIG_STYLE") or "v3").strip().lower() or "v3"


def _graphrag_cli_bin(python_bin: str) -> str | None:
    candidate = Path(str(python_bin)).resolve()
    if candidate.exists():
        if os.name == "nt":
            exe = candidate.parent / "graphrag.exe"
            if exe.exists():
                return str(exe)
        else:
            exe = candidate.parent / "graphrag"
            if exe.exists():
                return str(exe)
    resolved = shutil.which("graphrag")
    return resolved


def _build_index_command(*, python_bin: str, workspace_dir: Path, workspace_env: Dict[str, str]) -> List[str]:
    style = _runtime_style(workspace_env)
    use_cli = style != "legacy"
    if use_cli:
        graphrag_cli = _graphrag_cli_bin(python_bin)
        if graphrag_cli:
            command = [graphrag_cli, "index", "--root", str(workspace_dir)]
        else:
            command = [
                python_bin,
                "-c",
                "from graphrag.cli.main import app; app()",
                "index",
                "--root",
                str(workspace_dir),
            ]
    else:
        command = [python_bin, "-m", "graphrag.index", "--root", str(workspace_dir)]
    indexing_method = str(workspace_env.get("GRAPHRAG_INDEXING_METHOD") or "").strip().lower()
    if indexing_method and indexing_method != "standard":
        command.extend(["--method", indexing_method])
    return command


def _looks_like_artifacts_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    legacy_markers = (
        "create_final_documents.parquet",
        "create_final_text_units.parquet",
        "create_final_entities.parquet",
        "create_final_relationships.parquet",
    )
    v3_markers = (
        "documents.parquet",
        "text_units.parquet",
        "entities.parquet",
        "relationships.parquet",
    )
    partial_markers = (
        "create_base_text_units.parquet",
        "create_base_extracted_entities.parquet",
        "create_summarized_entities.parquet",
    )
    return any((path / name).exists() for name in (*legacy_markers, *v3_markers, *partial_markers))


def _resolve_output_layout(output_root: Path) -> tuple[Path | None, Path | None, Path | None]:
    try:
        candidates = [path for path in output_root.iterdir() if path.is_dir()]
    except FileNotFoundError:
        return None, None, None

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        artifacts_dir = candidate / "artifacts"
        reports_dir = candidate / "reports"
        if _looks_like_artifacts_dir(artifacts_dir):
            return candidate, artifacts_dir, reports_dir if reports_dir.exists() else None
        if _looks_like_artifacts_dir(candidate):
            if candidate.name.lower() == "artifacts":
                parent = candidate.parent
                parent_reports = parent / "reports"
                return parent, candidate, parent_reports if parent_reports.exists() else None
            return candidate, candidate, reports_dir if reports_dir.exists() else None

    root_artifacts_dir = output_root / "artifacts"
    root_reports_dir = output_root / "reports"
    if _looks_like_artifacts_dir(root_artifacts_dir):
        return output_root, root_artifacts_dir, root_reports_dir if root_reports_dir.exists() else None
    if _looks_like_artifacts_dir(output_root):
        return output_root, output_root, root_reports_dir if root_reports_dir.exists() else None

    latest_dir = candidates[0] if candidates else None
    if latest_dir is None:
        return None, None, None
    reports_dir = latest_dir / "reports"
    return latest_dir, None, reports_dir if reports_dir.exists() else None


def _rewrite_skip_workflows(settings_text: str, workflows: List[str]) -> str:
    rendered = ", ".join(json.dumps(str(item), ensure_ascii=False) for item in workflows)
    replacement = f"skip_workflows: [{rendered}]"
    lines = settings_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("skip_workflows:"):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if settings_text.endswith("\n") else "")
    return f"{replacement}\n{settings_text}"


def _rewrite_workflows(settings_text: str, workflows: List[str]) -> str:
    rendered = ", ".join(json.dumps(str(item), ensure_ascii=False) for item in workflows)
    replacement = f"workflows: [{rendered}]"
    lines = settings_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("workflows:"):
            lines[index] = replacement
            return "\n".join(lines) + ("\n" if settings_text.endswith("\n") else "")
    return f"{replacement}\n{settings_text}"


def _default_v3_workflows(indexing_method: str) -> List[str]:
    method = str(indexing_method or "standard").strip().lower() or "standard"
    if method == "fast":
        return [
            "load_input_documents",
            "create_base_text_units",
            "create_final_documents",
            "extract_graph_nlp",
            "prune_graph",
            "finalize_graph",
            "create_communities",
            "create_final_text_units",
            "create_community_reports_text",
            "generate_text_embeddings",
        ]
    return [
        "load_input_documents",
        "create_base_text_units",
        "create_final_documents",
        "extract_graph",
        "finalize_graph",
        "extract_covariates",
        "create_communities",
        "create_final_text_units",
        "create_community_reports",
        "generate_text_embeddings",
    ]


def _execution_mode(workspace_env: Dict[str, str]) -> str:
    return str(workspace_env.get("GRAPHRAG_EXECUTION_MODE") or "graphrag").strip().lower() or "graphrag"


def _is_deterministic_execution_mode(mode: str) -> bool:
    return mode in {"deterministic_local", "offline_local", "offline", "local_deterministic"}


def _safe_segment(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "").strip()).strip("-._")
    return cleaned or fallback


def _workspace_timestamp(workspace_env: Dict[str, str]) -> str:
    raw = str(workspace_env.get("timestamp") or workspace_env.get("TIMESTAMP") or "").strip()
    if raw:
        return _safe_segment(raw, "runtime")
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _expand_workspace_template_path(template: str, *, workspace_dir: Path, timestamp: str) -> Path:
    rendered = str(template or "").strip()
    rendered = rendered.replace("${timestamp}", timestamp).replace("$timestamp", timestamp)
    target = Path(rendered)
    if not target.is_absolute():
        target = (workspace_dir / target).resolve()
    return target


def _resolve_deterministic_output_layout(
    *,
    workspace_dir: Path,
    workspace_env: Dict[str, str],
) -> tuple[Path, Path, Path]:
    timestamp = _workspace_timestamp(workspace_env)
    storage_dir_template = str(workspace_env.get("GRAPHRAG_STORAGE_DIR") or "output/${timestamp}/artifacts").strip()
    reporting_dir_template = str(workspace_env.get("GRAPHRAG_REPORTING_DIR") or "output/${timestamp}/reports").strip()
    artifacts_dir = _expand_workspace_template_path(
        storage_dir_template,
        workspace_dir=workspace_dir,
        timestamp=timestamp,
    )
    reports_dir = _expand_workspace_template_path(
        reporting_dir_template,
        workspace_dir=workspace_dir,
        timestamp=timestamp,
    )
    if artifacts_dir.name.lower() == "artifacts":
        output_dir = artifacts_dir.parent
    else:
        output_dir = artifacts_dir
        artifacts_dir = output_dir / "artifacts"
    return output_dir, artifacts_dir, reports_dir


def _split_text_chunks(text: str, *, max_chunks: int = 4, max_chars: int = 420) -> List[str]:
    normalized = str(text or "").replace("\r\n", "\n")
    sections = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
    chunks: List[str] = []
    for section in sections:
        current = section
        while len(current) > max_chars:
            head = current[:max_chars].rstrip()
            if head:
                chunks.append(head)
            current = current[max_chars:].lstrip()
            if len(chunks) >= max_chunks:
                break
        if len(chunks) >= max_chunks:
            break
        if current:
            chunks.append(current)
        if len(chunks) >= max_chunks:
            break
    if not chunks and normalized.strip():
        chunks = [normalized.strip()[:max_chars]]
    return chunks[:max_chunks]


def _extract_entity_candidates(text: str, *, cap: int = 8) -> List[str]:
    blocked = {
        "json",
        "result",
        "confidence",
        "source_ref_id",
        "diagnostics",
        "trace_hits",
        "table",
        "figure",
        "field",
        "document",
        "chunk",
        "module2",
    }
    candidates: List[str] = []
    seen: set[str] = set()

    patterns = (
        r"[:：]\s*([A-Za-z][A-Za-z0-9_. -]{1,40})",
        r"[:：]\s*([\u4e00-\u9fff]{2,16})",
        r"\b([A-Z][A-Za-z0-9_-]{2,24})\b",
        r"([\u4e00-\u9fff]{2,12})",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text):
            token = str(match).strip(" ,.;:()[]{}<>\"'")
            if not token:
                continue
            lowered = token.lower()
            if lowered in blocked:
                continue
            if token in seen:
                continue
            seen.add(token)
            candidates.append(token)
            if len(candidates) >= cap:
                return candidates
    return candidates


def _load_workspace_text_inputs(*, workspace_dir: Path, workspace_env: Dict[str, str]) -> List[Dict[str, str]]:
    input_dir_name = str(workspace_env.get("GRAPHRAG_INPUT_DIR") or "input").strip() or "input"
    input_dir = (workspace_dir / input_dir_name).resolve()
    if not input_dir.exists():
        return []

    rows: List[Dict[str, str]] = []
    for index, path in enumerate(sorted(input_dir.glob("*.txt")), start=1):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            text = ""
        if not text:
            continue
        stem = _safe_segment(path.stem, f"document-{index}")
        rows.append(
            {
                "doc_id": f"doc-{index}",
                "title": path.stem.replace("_", " ").strip() or f"Document {index}",
                "raw_content": text,
                "human_readable_id": str(index),
                "source_path": str(path),
                "stem": stem,
            }
        )
    return rows


def _write_parquet_rows(path: Path, rows: List[Dict[str, Any]], *, columns: List[str]) -> None:
    import pandas as pd

    frame = pd.DataFrame(rows)
    if frame.empty:
        frame = pd.DataFrame(columns=columns)
    else:
        for column in columns:
            if column not in frame.columns:
                frame[column] = None
        frame = frame.loc[:, columns]
    frame.to_parquet(path, index=False)


def _build_deterministic_artifacts(*, workspace_dir: Path, workspace_env: Dict[str, str]) -> tuple[Path, Path, Path]:
    output_dir, artifacts_dir, reports_dir = _resolve_deterministic_output_layout(
        workspace_dir=workspace_dir,
        workspace_env=workspace_env,
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    inputs = _load_workspace_text_inputs(workspace_dir=workspace_dir, workspace_env=workspace_env)
    if not inputs:
        raise RuntimeError("No normalized input documents were found under workspace input directory")

    documents: List[Dict[str, Any]] = []
    text_units: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    communities: List[Dict[str, Any]] = []
    community_reports: List[Dict[str, Any]] = []

    entity_index: Dict[str, Dict[str, Any]] = {}
    relationship_seen: set[tuple[str, str, str]] = set()

    chunk_seq = 0
    entity_seq = 0
    relationship_seq = 0

    all_chunk_ids: List[str] = []
    all_relationship_ids: List[str] = []
    community_id = "community-1"

    for document in inputs:
        doc_id = str(document["doc_id"])
        doc_chunks = _split_text_chunks(document["raw_content"])
        doc_chunk_ids: List[str] = []

        for chunk_text in doc_chunks:
            chunk_seq += 1
            chunk_id = f"chunk-{chunk_seq}"
            doc_chunk_ids.append(chunk_id)
            all_chunk_ids.append(chunk_id)

            chunk_entities = _extract_entity_candidates(chunk_text, cap=4)
            if not chunk_entities:
                fallback_name = _safe_segment(document["title"], f"entity-{chunk_seq}").replace("-", "_")
                chunk_entities = [fallback_name]

            chunk_entity_ids: List[str] = []
            for entity_name in chunk_entities:
                key = entity_name.lower()
                entity_row = entity_index.get(key)
                if entity_row is None:
                    entity_seq += 1
                    entity_row = {
                        "id": f"entity-{entity_seq}",
                        "name": entity_name,
                        "type": "concept",
                        "description": f"{entity_name} appears in the indexed document context.",
                        "human_readable_id": str(entity_seq),
                        "text_unit_ids": [],
                        "community_ids": [community_id],
                    }
                    entity_index[key] = entity_row
                    entities.append(entity_row)
                if chunk_id not in entity_row["text_unit_ids"]:
                    entity_row["text_unit_ids"].append(chunk_id)
                chunk_entity_ids.append(str(entity_row["id"]))

            if len(chunk_entity_ids) >= 2:
                source_entity = next(item for item in entities if str(item["id"]) == chunk_entity_ids[0])
                target_entity = next(item for item in entities if str(item["id"]) == chunk_entity_ids[1])
                relation_key = (str(source_entity["name"]), str(target_entity["name"]), chunk_id)
                if relation_key not in relationship_seen:
                    relationship_seen.add(relation_key)
                    relationship_seq += 1
                    relationship_id = f"relationship-{relationship_seq}"
                    relationships.append(
                        {
                            "id": relationship_id,
                            "source": source_entity["name"],
                            "target": target_entity["name"],
                            "rank": 1.0,
                            "combined_degree": 1.0,
                            "weight": 1.0,
                            "human_readable_id": str(relationship_seq),
                            "description": (
                                f"{source_entity['name']} is semantically related to {target_entity['name']} "
                                f"within document chunk {chunk_id}."
                            ),
                            "text_unit_ids": [chunk_id],
                        }
                    )
                    all_relationship_ids.append(relationship_id)

            text_units.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "n_tokens": max(1, len(chunk_text.split())),
                    "document_ids": [doc_id],
                    "document_id": doc_id,
                    "entity_ids": chunk_entity_ids,
                    "relationship_ids": [item["id"] for item in relationships if chunk_id in item.get("text_unit_ids", [])],
                    "covariate_ids": [],
                    "human_readable_id": str(chunk_seq),
                }
            )

        documents.append(
            {
                "id": doc_id,
                "title": document["title"],
                "raw_content": document["raw_content"],
                "text_unit_ids": doc_chunk_ids,
                "human_readable_id": document["human_readable_id"],
            }
        )

    if len(entities) < 2:
        while len(entities) < 2:
            entity_seq += 1
            name = f"Entity_{entity_seq}"
            entities.append(
                {
                    "id": f"entity-{entity_seq}",
                    "name": name,
                    "type": "concept",
                    "description": f"{name} is a deterministic placeholder entity.",
                    "human_readable_id": str(entity_seq),
                    "text_unit_ids": [all_chunk_ids[0]] if all_chunk_ids else [],
                    "community_ids": [community_id],
                }
            )
        if all_chunk_ids:
            relationship_seq += 1
            relationship_id = f"relationship-{relationship_seq}"
            relationships.append(
                {
                    "id": relationship_id,
                    "source": entities[0]["name"],
                    "target": entities[1]["name"],
                    "rank": 1.0,
                    "combined_degree": 1.0,
                    "weight": 1.0,
                    "human_readable_id": str(relationship_seq),
                    "description": f"{entities[0]['name']} is related to {entities[1]['name']}.",
                    "text_unit_ids": [all_chunk_ids[0]],
                }
            )
            all_relationship_ids.append(relationship_id)

    communities.append(
        {
            "id": community_id,
            "community": community_id,
            "community_id": community_id,
            "level": 0,
            "title": "Deterministic Community",
            "text_unit_ids": list(all_chunk_ids),
            "relationship_ids": list(all_relationship_ids),
        }
    )
    community_reports.append(
        {
            "id": "community-report-1",
            "report_id": "community-report-1",
            "human_readable_id": "1",
            "community": community_id,
            "community_id": community_id,
            "title": "Deterministic Community Report",
            "summary": "This report summarizes key entities and relationships extracted from normalized document text.",
            "full_content": (
                "Deterministic local index generated a stable graph snapshot. "
                "Entities and relationships are linked to document chunks for evidence tracing."
            ),
            "level": 0,
            "rank": 1.0,
            "rank_explanation": "Deterministic baseline report for offline GraphRAG testing.",
            "findings": [
                {
                    "summary": "Entity linkage established",
                    "explanation": "At least one RELATED relationship is connected through chunk evidence.",
                }
            ],
            "text_unit_ids": list(all_chunk_ids),
        }
    )

    _write_parquet_rows(
        artifacts_dir / "documents.parquet",
        documents,
        columns=["id", "title", "raw_content", "text_unit_ids", "human_readable_id"],
    )
    _write_parquet_rows(
        artifacts_dir / "text_units.parquet",
        text_units,
        columns=[
            "id",
            "text",
            "n_tokens",
            "document_ids",
            "document_id",
            "entity_ids",
            "relationship_ids",
            "covariate_ids",
            "human_readable_id",
        ],
    )
    _write_parquet_rows(
        artifacts_dir / "entities.parquet",
        entities,
        columns=["id", "name", "type", "description", "human_readable_id", "text_unit_ids", "community_ids"],
    )
    _write_parquet_rows(
        artifacts_dir / "relationships.parquet",
        relationships,
        columns=[
            "id",
            "source",
            "target",
            "rank",
            "combined_degree",
            "weight",
            "human_readable_id",
            "description",
            "text_unit_ids",
        ],
    )
    _write_parquet_rows(
        artifacts_dir / "communities.parquet",
        communities,
        columns=["id", "community", "community_id", "level", "title", "text_unit_ids", "relationship_ids"],
    )
    _write_parquet_rows(
        artifacts_dir / "community_reports.parquet",
        community_reports,
        columns=[
            "id",
            "report_id",
            "human_readable_id",
            "community",
            "community_id",
            "title",
            "summary",
            "full_content",
            "level",
            "rank",
            "rank_explanation",
            "findings",
            "text_unit_ids",
        ],
    )

    return output_dir, artifacts_dir, reports_dir


def _should_retry_without_community_reports(log_path: Path) -> bool:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False
    if "create_community_reports" in text:
        if (
            "Failed to generate valid JSON output" in text
            or "error generating community report" in text
            or "error running workflow create_community_reports" in text
            or "Errors occurred during the pipeline run" in text
        ):
            return True
    if "create_final_community_reports" not in text:
        return False
    return (
        "Failed to generate valid JSON output" in text
        or "error generating community report" in text
        or "error running workflow create_final_community_reports" in text
        or "Errors occurred during the pipeline run" in text
        or "✗ create_final_community_reports" in text
        or "鉂?create_final_community_reports" in text
    )


def _detect_runtime_binary_incompatibility(log_path: Path) -> str | None:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    lower = text.lower()
    required_signatures = (
        "numpy.dtype size changed",
        "scipy.spatial._ckdtree",
    )
    if not all(signature in lower for signature in required_signatures):
        return None
    return (
        "Detected NumPy/SciPy binary incompatibility in GraphRAG runtime. "
        "Please pin compatible versions (for example: numpy>=1.26.4,<2.0 and scipy>=1.12,<1.13) "
        "and reinstall module4 dependencies."
    )


def _detect_retryable_process_failure(log_path: Path) -> str | None:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    lower = text.lower()

    cache_missing_signature = (
        ("no such file or directory" in lower or "filenotfounderror" in lower)
        and "cache" in lower
        and "summarize_descriptions" in lower
    )
    if cache_missing_signature:
        return "cache_missing_summarize_descriptions"

    rate_limited_signature = (
        "ratelimiterror" in lower
        or "error code: 429" in lower
        or "http 429" in lower
        or ("failed to validate embedding model" in lower and "429" in lower)
    )
    if rate_limited_signature:
        return "provider_rate_limited"

    return None


def _resolve_workspace_subdir(workspace_dir: Path, raw_value: str, fallback: str) -> Path | None:
    value = str(raw_value or "").strip() or fallback
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (workspace_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    try:
        candidate.relative_to(workspace_dir)
    except ValueError:
        return None
    return candidate


def _reset_workspace_runtime_dirs(
    *,
    workspace_dir: Path,
    workspace_env: Dict[str, str],
    reset_cache: bool,
    reset_output: bool,
) -> List[str]:
    touched: List[str] = []

    if reset_cache:
        cache_dir = _resolve_workspace_subdir(
            workspace_dir,
            str(workspace_env.get("GRAPHRAG_CACHE_DIR") or "cache"),
            "cache",
        )
        if cache_dir is not None:
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            touched.append(str(cache_dir))

    if reset_output:
        output_dir = _resolve_workspace_subdir(workspace_dir, "output", "output")
        if output_dir is not None:
            if output_dir.exists():
                shutil.rmtree(output_dir, ignore_errors=True)
            output_dir.mkdir(parents=True, exist_ok=True)
            touched.append(str(output_dir))

    return touched


@dataclass(frozen=True)
class GraphRAGIndexResult:
    command: List[str]
    log_path: Path
    output_dir: Path | None
    artifacts_dir: Path | None
    reports_dir: Path | None
    skipped_workflows: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphRAGIndexError(RuntimeError):
    category: str
    message: str
    log_path: Path
    exit_code: int | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class GraphRAGDependencyProbe:
    configured: bool
    reachable: Optional[bool] = None
    missing_fields: List[str] = field(default_factory=list)
    error_message: str | None = None

    def as_dict(self) -> Dict[str, object]:
        return {
            "configured": self.configured,
            "reachable": self.reachable,
            "missing_fields": list(self.missing_fields),
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class GraphRAGRuntimeProbe:
    ready: bool
    check_mode: str
    python_bin: str
    python_bin_exists: bool
    graphrag_module_available: bool
    module_error_message: str | None
    prompt_assets_root: str
    prompt_assets_ok: bool
    missing_prompt_assets: List[str] = field(default_factory=list)
    config_missing_fields: List[str] = field(default_factory=list)
    runtime_versions: Dict[str, str] = field(default_factory=dict)
    runtime_profile: Dict[str, object] = field(default_factory=dict)
    env_mapping: Dict[str, Dict[str, str]] = field(default_factory=dict)
    tiktoken_encoding_ready: Optional[bool] = None
    tiktoken_encoding_error_message: str | None = None
    provider_api: GraphRAGDependencyProbe = field(default_factory=lambda: GraphRAGDependencyProbe(configured=False))
    neo4j: GraphRAGDependencyProbe = field(default_factory=lambda: GraphRAGDependencyProbe(configured=False))

    def as_dict(self) -> Dict[str, object]:
        return {
            "ready": self.ready,
            "check_mode": self.check_mode,
            "python_bin": self.python_bin,
            "python_bin_exists": self.python_bin_exists,
            "graphrag_module_available": self.graphrag_module_available,
            "module_error_message": self.module_error_message,
            "prompt_assets_root": self.prompt_assets_root,
            "prompt_assets_ok": self.prompt_assets_ok,
            "missing_prompt_assets": list(self.missing_prompt_assets),
            "config_missing_fields": list(self.config_missing_fields),
            "runtime_versions": dict(self.runtime_versions),
            "runtime_profile": dict(self.runtime_profile),
            "env_mapping": {str(key): dict(value) for key, value in self.env_mapping.items()},
            "tiktoken_encoding_ready": self.tiktoken_encoding_ready,
            "tiktoken_encoding_error_message": self.tiktoken_encoding_error_message,
            "provider_api": self.provider_api.as_dict(),
            "neo4j": self.neo4j.as_dict(),
        }

    def summary(self) -> str:
        parts: List[str] = []
        if self.config_missing_fields:
            parts.append(f"missing config: {', '.join(self.config_missing_fields)}")
        if not self.python_bin_exists:
            parts.append(f"python executable not found: {self.python_bin}")
        if not self.graphrag_module_available:
            parts.append(self.module_error_message or "graphrag package is not available")
        if self.missing_prompt_assets:
            parts.append(f"missing prompt assets: {', '.join(self.missing_prompt_assets)}")
        if self.tiktoken_encoding_ready is False:
            parts.append(self.tiktoken_encoding_error_message or "tiktoken encoding is not available")
        if self.provider_api.configured and self.provider_api.reachable is False:
            parts.append(self.provider_api.error_message or "Provider API endpoint is not reachable")
        if not parts:
            parts.append("runtime ready")
        return "; ".join(parts)


def _python_bin_exists(python_bin: str) -> bool:
    if not python_bin:
        return False
    candidate = Path(python_bin)
    if candidate.is_absolute():
        return candidate.exists()
    return shutil.which(python_bin) is not None


def _python_supports_module(python_bin: str, module_name: str) -> tuple[bool, str | None]:
    if not _python_bin_exists(python_bin):
        return False, f"Configured python executable not found: {python_bin}"
    try:
        completed = subprocess.run(
            [
                python_bin,
                "-c",
                (
                    "import importlib.util, sys; "
                    f"sys.stdout.write('1' if importlib.util.find_spec({module_name!r}) else '0')"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timed out while checking module availability: {module_name}"
    except FileNotFoundError:
        return False, f"Configured python executable not found: {python_bin}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Unable to inspect python runtime: {type(exc).__name__}: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return False, detail or f"Module check failed for {module_name}"
    if (completed.stdout or "").strip() == "1":
        return True, None
    return False, f"Python runtime does not have module installed: {module_name}"


def _python_runtime_details(python_bin: str) -> tuple[Dict[str, str], Optional[bool], str | None]:
    if not _python_bin_exists(python_bin):
        return {}, None, f"Configured python executable not found: {python_bin}"

    try:
        completed = subprocess.run(
            [
                python_bin,
                "-c",
                (
                    "import json, importlib.metadata as md\n"
                    "payload = {'versions': {}, 'tiktoken_encoding_ready': None, 'tiktoken_encoding_error': None}\n"
                    "for name in ('python', 'graphrag', 'tiktoken', 'pandas', 'datashaper'):\n"
                    "    try:\n"
                    "        if name == 'python':\n"
                    "            import sys\n"
                    "            payload['versions'][name] = sys.version.split()[0]\n"
                    "        else:\n"
                    "            payload['versions'][name] = md.version(name)\n"
                    "    except Exception:\n"
                    "        continue\n"
                    "try:\n"
                    "    import tiktoken\n"
                    "    tiktoken.get_encoding('cl100k_base')\n"
                    "    payload['tiktoken_encoding_ready'] = True\n"
                    "except Exception as exc:\n"
                    "    payload['tiktoken_encoding_ready'] = False\n"
                    "    payload['tiktoken_encoding_error'] = f'{type(exc).__name__}: {exc}'\n"
                    "print(json.dumps(payload, ensure_ascii=False))\n"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {}, None, "Timed out while inspecting python runtime details"
    except FileNotFoundError:
        return {}, None, f"Configured python executable not found: {python_bin}"
    except Exception as exc:  # pragma: no cover - defensive
        return {}, None, f"Unable to inspect python runtime details: {type(exc).__name__}: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return {}, None, detail or "Python runtime detail inspection failed"

    try:
        payload = json.loads((completed.stdout or "").strip() or "{}")
    except Exception as exc:
        return {}, None, f"Unable to parse python runtime details: {type(exc).__name__}: {exc}"

    raw_versions = payload.get("versions") if isinstance(payload.get("versions"), dict) else {}
    versions = {str(key): str(value) for key, value in raw_versions.items() if str(value).strip()}
    encoding_ready = payload.get("tiktoken_encoding_ready")
    if encoding_ready is not None:
        encoding_ready = bool(encoding_ready)
    encoding_error = str(payload.get("tiktoken_encoding_error") or "").strip() or None
    return versions, encoding_ready, encoding_error


def _missing_prompt_assets(runtime: GraphRAGRuntimeSettings) -> List[str]:
    registry = PromptRegistry(asset_root=runtime.prompt_assets_root, overrides=runtime.prompt_overrides())
    missing: List[str] = []
    for key in registry.keys():
        path = registry.prompt_path(key)
        if not path.exists():
            missing.append(str(path))
    return missing


def _provider_api_status_url(api_base: str) -> str:
    base = str(api_base or "").rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    return f"{base}/api/status"


def _probe_provider_api(runtime: GraphRAGRuntimeSettings, *, check_remote: bool) -> GraphRAGDependencyProbe:
    missing_fields = ["MODULE4_GRAPHRAG_API_BASE"] if not runtime.api_base else []
    configured = not missing_fields
    if not configured:
        return GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=missing_fields)
    if not check_remote:
        return GraphRAGDependencyProbe(configured=True, reachable=None, missing_fields=[])

    url = _provider_api_status_url(runtime.api_base)
    request = urllib.request.Request(url, headers={"User-Agent": "module4-healthz/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            body = response.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
        ok = bool(payload.get("success", True))
        error_message = None if ok else f"Provider API status probe returned success={payload.get('success')}"
        return GraphRAGDependencyProbe(configured=True, reachable=ok, missing_fields=[], error_message=error_message)
    except urllib.error.HTTPError as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Provider API status probe failed with HTTP {exc.code}",
        )
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Provider API status probe failed: {type(exc).__name__}: {exc}",
        )


def _probe_neo4j(neo4j: Neo4jSettings, *, check_remote: bool) -> GraphRAGDependencyProbe:
    missing_fields = neo4j.missing_fields()
    configured = not missing_fields
    if not configured:
        return GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=missing_fields)
    if not check_remote:
        return GraphRAGDependencyProbe(configured=True, reachable=None, missing_fields=[])

    try:
        from neo4j import GraphDatabase
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Neo4j driver import failed: {type(exc).__name__}: {exc}",
        )

    driver = None
    try:
        driver = GraphDatabase.driver(
            neo4j.uri,
            auth=(neo4j.username, neo4j.password),
            connection_timeout=3.0,
            max_connection_pool_size=1,
        )
        driver.verify_connectivity()
        return GraphRAGDependencyProbe(configured=True, reachable=True, missing_fields=[])
    except Exception as exc:
        return GraphRAGDependencyProbe(
            configured=True,
            reachable=False,
            missing_fields=[],
            error_message=f"Neo4j connectivity probe failed: {type(exc).__name__}: {exc}",
        )
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:  # pragma: no cover - defensive
                pass


class GraphRAGIndexer:
    def __init__(self) -> None:
        self.python_bin = _resolve_python_bin()
        self.timeout_sec = max(60, int(os.getenv("MODULE4_GRAPHRAG_INDEX_TIMEOUT_SEC", "7200")))

    def probe(
        self,
        runtime: GraphRAGRuntimeSettings | None = None,
        neo4j: Neo4jSettings | None = None,
        *,
        check_remote: bool = False,
    ) -> GraphRAGRuntimeProbe:
        runtime = runtime or GraphRAGRuntimeSettings.from_env()
        neo4j = neo4j or Neo4jSettings.from_env()
        config_missing_fields = runtime.missing_fields()
        missing_prompt_assets = _missing_prompt_assets(runtime)
        python_exists = _python_bin_exists(self.python_bin)
        module_available, module_error = _python_supports_module(self.python_bin, "graphrag")
        runtime_versions, tiktoken_encoding_ready, tiktoken_encoding_error = _python_runtime_details(self.python_bin)
        provider_api_probe = _probe_provider_api(runtime, check_remote=check_remote)
        neo4j_probe = _probe_neo4j(neo4j, check_remote=check_remote)

        provider_api_ok = provider_api_probe.configured
        if check_remote:
            provider_api_ok = provider_api_probe.reachable is True

        ready = (
            not config_missing_fields
            and python_exists
            and module_available
            and not missing_prompt_assets
            and tiktoken_encoding_ready is not False
            and provider_api_ok
        )

        return GraphRAGRuntimeProbe(
            ready=ready,
            check_mode="deep" if check_remote else "basic",
            python_bin=self.python_bin,
            python_bin_exists=python_exists,
            graphrag_module_available=module_available,
            module_error_message=module_error,
            prompt_assets_root=str(runtime.prompt_assets_root),
            prompt_assets_ok=not missing_prompt_assets,
            missing_prompt_assets=missing_prompt_assets,
            config_missing_fields=config_missing_fields,
            runtime_versions=runtime_versions,
            runtime_profile={
                "config_style": runtime.config_style,
                "use_source_checkout": runtime.use_source_checkout,
                "source_repo_root": runtime.source_repo_root,
                "indexing_method": runtime.indexing_method,
                "execution_mode": str(runtime.execution_mode or "graphrag"),
                "workflows": list(runtime.workflows),
                "skip_workflows": list(runtime.skip_workflows),
                "retry_skip_community_reports": runtime.retry_skip_community_reports,
                "chunk_size": runtime.chunk_size,
                "chunk_overlap": runtime.chunk_overlap,
                "max_tokens": runtime.max_tokens,
            },
            env_mapping=runtime.env_mapping(),
            tiktoken_encoding_ready=tiktoken_encoding_ready,
            tiktoken_encoding_error_message=tiktoken_encoding_error,
            provider_api=provider_api_probe,
            neo4j=neo4j_probe,
        )

    def run(self, workspace_dir: Path) -> GraphRAGIndexResult:
        workspace_dir = workspace_dir.resolve()
        env = os.environ.copy()
        workspace_env = _workspace_env_file(workspace_dir / ".env")
        env.update(workspace_env)
        env = _augment_source_checkout_env(env, workspace_env)
        execution_mode = _execution_mode(workspace_env)
        style = _runtime_style(workspace_env)
        allow_retry_skip_community_reports = _retry_skip_community_reports_enabled(workspace_env)
        community_retry_workflow = "create_final_community_reports" if style == "legacy" else "create_community_reports"
        process_retry_max_attempts_raw = str(
            os.getenv("MODULE4_GRAPHRAG_RETRY_PROCESS_MAX_ATTEMPTS", "1")
        ).strip()
        try:
            process_retry_max_attempts = max(0, int(process_retry_max_attempts_raw or "1"))
        except ValueError:
            process_retry_max_attempts = 1
        process_retry_backoff_raw = str(
            os.getenv("MODULE4_GRAPHRAG_RETRY_PROCESS_BACKOFF_SEC", "8")
        ).strip()
        try:
            process_retry_backoff_sec = max(0.0, float(process_retry_backoff_raw or "8"))
        except ValueError:
            process_retry_backoff_sec = 8.0

        log_path = workspace_dir / "graphrag-index.log"
        if _is_deterministic_execution_mode(execution_mode):
            try:
                output_dir, artifacts_dir, reports_dir = _build_deterministic_artifacts(
                    workspace_dir=workspace_dir,
                    workspace_env=workspace_env,
                )
            except Exception as exc:
                try:
                    with log_path.open("a", encoding="utf-8") as log_file:
                        log_file.write(
                            f"\n# module4 deterministic index failed: {type(exc).__name__}: {exc}\n"
                        )
                except Exception:
                    pass
                raise GraphRAGIndexError(
                    category="deterministic_index_failed",
                    message=f"Deterministic GraphRAG index failed: {type(exc).__name__}: {exc}. See {log_path}",
                    log_path=log_path,
                ) from exc
            command = ["module4-deterministic-index", "--root", str(workspace_dir)]
            try:
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(
                        f"\n# module4 deterministic index success (mode={execution_mode})\n"
                        f"$ {' '.join(command)}\n"
                    )
            except Exception:
                pass
            return GraphRAGIndexResult(
                command=command,
                log_path=log_path,
                output_dir=output_dir,
                artifacts_dir=artifacts_dir,
                reports_dir=reports_dir if reports_dir.exists() else None,
                skipped_workflows=[],
            )

        command = _build_index_command(
            python_bin=self.python_bin,
            workspace_dir=workspace_dir,
            workspace_env=workspace_env,
        )

        def _execute() -> subprocess.CompletedProcess[str]:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"$ {' '.join(command)}\n")
                log_file.flush()
                try:
                    return subprocess.run(
                        command,
                        cwd=str(workspace_dir),
                        env=env,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=self.timeout_sec,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise GraphRAGIndexError(
                        category="index_timeout",
                        message=f"GraphRAG index timed out after {self.timeout_sec}s. See {log_path}",
                        log_path=log_path,
                    ) from exc

        skipped_workflows: List[str] = []
        completed = _execute()
        try:
            log_path.touch(exist_ok=True)
        except Exception:  # pragma: no cover - defensive
            pass

        if completed.returncode != 0:
            settings_path = workspace_dir / "settings.yaml"
            should_retry_without_reports = False
            if allow_retry_skip_community_reports:
                should_retry_without_reports = _should_retry_without_community_reports(log_path)
                if not should_retry_without_reports:
                    _, partial_artifacts_dir, _ = _resolve_output_layout(workspace_dir / "output")
                    if partial_artifacts_dir is not None:
                        has_entities = any(
                            (partial_artifacts_dir / name).exists()
                            for name in ("create_final_entities.parquet", "entities.parquet")
                        )
                        has_relationships = any(
                            (partial_artifacts_dir / name).exists()
                            for name in ("create_final_relationships.parquet", "relationships.parquet")
                        )
                        missing_community_reports = not any(
                            (partial_artifacts_dir / name).exists()
                            for name in ("create_final_community_reports.parquet", "community_reports.parquet")
                        )
                        should_retry_without_reports = has_entities and has_relationships and missing_community_reports

            if should_retry_without_reports:
                try:
                    original = settings_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    original = None
                if original is not None:
                    skipped_workflows = [community_retry_workflow]
                    updated = _rewrite_skip_workflows(original, skipped_workflows)
                    if style != "legacy":
                        retry_workflows = [
                            workflow
                            for workflow in _default_v3_workflows(str(workspace_env.get("GRAPHRAG_INDEXING_METHOD") or ""))
                            if workflow != community_retry_workflow
                        ]
                        if retry_workflows:
                            updated = _rewrite_workflows(updated, retry_workflows)
                    if updated != original:
                        settings_path.write_text(updated, encoding="utf-8")
                    with log_path.open("a", encoding="utf-8") as log_file:
                        log_file.write(
                            f"\n# module4 retry: skip_workflows=[\"{community_retry_workflow}\"] due to unstable community report JSON\n"
                        )
                    completed = _execute()
            if completed.returncode != 0 and process_retry_max_attempts > 0:
                reason_labels = {
                    "cache_missing_summarize_descriptions": "cache file miss under summarize_descriptions",
                    "provider_rate_limited": "provider rate limited (429)",
                }
                for attempt in range(1, process_retry_max_attempts + 1):
                    retry_reason = _detect_retryable_process_failure(log_path)
                    if retry_reason is None:
                        break

                    reset_cache = retry_reason == "cache_missing_summarize_descriptions"
                    reset_output = True
                    touched_dirs = _reset_workspace_runtime_dirs(
                        workspace_dir=workspace_dir,
                        workspace_env=workspace_env,
                        reset_cache=reset_cache,
                        reset_output=reset_output,
                    )
                    reason_label = reason_labels.get(retry_reason, retry_reason)
                    backoff_sec = process_retry_backoff_sec * attempt if retry_reason == "provider_rate_limited" else 0.0
                    with log_path.open("a", encoding="utf-8") as log_file:
                        touched_text = ", ".join(touched_dirs) if touched_dirs else "(none)"
                        log_file.write(
                            "\n# module4 retry: "
                            f"attempt={attempt}/{process_retry_max_attempts} "
                            f"reason={reason_label} "
                            f"reset_cache={str(reset_cache).lower()} "
                            f"reset_output={str(reset_output).lower()} "
                            f"touched={touched_text}\n"
                        )
                        if backoff_sec > 0:
                            log_file.write(
                                f"# module4 retry: provider backoff {backoff_sec:.1f}s before re-run\n"
                            )
                    if backoff_sec > 0:
                        time.sleep(backoff_sec)
                    completed = _execute()
                    if completed.returncode == 0:
                        break
            if completed.returncode != 0:
                binary_incompat_message = _detect_runtime_binary_incompatibility(log_path)
                if binary_incompat_message:
                    raise GraphRAGIndexError(
                        category="runtime_binary_incompatible",
                        message=f"{binary_incompat_message} See {log_path}",
                        log_path=log_path,
                        exit_code=completed.returncode,
                    )
                raise GraphRAGIndexError(
                    category="index_process_failed",
                    message=f"GraphRAG index failed with exit code {completed.returncode}. See {log_path}",
                    log_path=log_path,
                    exit_code=completed.returncode,
                )

        output_root = workspace_dir / "output"
        output_dir, artifacts_dir, reports_dir = _resolve_output_layout(output_root)
        if not output_dir or not artifacts_dir or not artifacts_dir.exists():
            raise GraphRAGIndexError(
                category="artifacts_missing",
                message=f"GraphRAG index finished but no artifacts directory was produced under {output_root}",
                log_path=log_path,
            )

        return GraphRAGIndexResult(
            command=command,
            log_path=log_path,
            output_dir=output_dir,
            artifacts_dir=artifacts_dir,
            reports_dir=reports_dir if reports_dir and reports_dir.exists() else None,
            skipped_workflows=skipped_workflows,
        )

    def inspect_output(self, workspace_dir: Path) -> GraphRAGIndexResult:
        workspace_dir = workspace_dir.resolve()
        log_path = workspace_dir / "graphrag-index.log"
        workspace_env = _workspace_env_file(workspace_dir / ".env")
        command = _build_index_command(
            python_bin=self.python_bin,
            workspace_dir=workspace_dir,
            workspace_env=workspace_env,
        )
        output_root = workspace_dir / "output"
        output_dir, artifacts_dir, reports_dir = _resolve_output_layout(output_root)
        return GraphRAGIndexResult(
            command=command,
            log_path=log_path,
            output_dir=output_dir,
            artifacts_dir=artifacts_dir,
            reports_dir=reports_dir if reports_dir and reports_dir.exists() else None,
            skipped_workflows=[],
        )
