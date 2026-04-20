from __future__ import annotations

import asyncio
import json
import sys
import types
from importlib import import_module
from pathlib import Path
from typing import Any, Dict

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


query_service = import_module("app.modules.module4.services.graphrag.query_service")


@pytest.fixture(autouse=True)
def _force_inprocess_query_execution(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_EXECUTION_MODE", "inprocess")


class _QueryStorage:
    def __init__(self, *, graph_file: Dict[str, Any], graph_version: Dict[str, Any]) -> None:
        self._graph_file = dict(graph_file)
        self._graph_version = dict(graph_version)
        self.graph_version_calls: list[tuple[str, str]] = []

    async def get_graph_file(self, *, tenant_id: str, file_hash: str) -> Dict[str, Any] | None:
        if tenant_id != str(self._graph_file.get("tenant_id") or ""):
            return None
        if file_hash != str(self._graph_file.get("file_hash") or ""):
            return None
        return dict(self._graph_file)

    async def get_graph_version(self, *, tenant_id: str, graph_version_id: str) -> Dict[str, Any] | None:
        self.graph_version_calls.append((tenant_id, graph_version_id))
        if tenant_id != str(self._graph_version.get("tenant_id") or ""):
            return None
        if graph_version_id != str(self._graph_version.get("graph_version_id") or ""):
            return None
        return dict(self._graph_version)


def test_search_graph_returns_public_case_identity_while_reading_source_tenant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    registry_path = (tmp_path / "public_case_graphs.json").resolve()
    registry_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "case-query",
                    "display_name": "案例图谱·问答校验（DOCX）",
                    "source_tenant_id": "tenant-public-source",
                    "source_file_hash": "hash-public",
                    "sort_order": 10,
                    "enabled": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODULE4_PUBLIC_CASE_REGISTRY_PATH", str(registry_path))

    workspace_dir = (tmp_path / "workspace").resolve()
    artifacts_dir = (workspace_dir / "output" / "snapshot" / "artifacts").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "settings.yaml").write_text("encoding_model: cl100k_base\n", encoding="utf-8")
    manifest_path = (workspace_dir / "manifest.json").resolve()
    manifest_path.write_text("{}", encoding="utf-8")

    storage = _QueryStorage(
        graph_file={
            "graph_file_id": "gf_public_source",
            "tenant_id": "tenant-public-source",
            "file_hash": "hash-public",
            "file_name": "source-public.docx",
            "workspace_id": "ws_public",
            "active_version_id": "ver_public_1",
            "metadata": {},
        },
        graph_version={
            "tenant_id": "tenant-public-source",
            "graph_version_id": "ver_public_1",
            "artifacts_dir": str(artifacts_dir),
            "manifest_path": str(manifest_path),
            "workspace_id": "ws_public",
        },
    )

    async def _fake_execute_query_runtime(**_: Any) -> Dict[str, Any]:
        return {
            "answer": "public case answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local",
        }

    async def _fake_canonicalize(**_: Any):
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "resolution_strategy": "storage_only",
            "used_fallback_candidates": False,
        }

    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setattr(
        query_service,
        "_canonicalize_linked_node_ids_with_storage_diagnostics",
        _fake_canonicalize,
    )

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = asyncio.run(
        query_service.search_graph(
            storage=storage,
            tenant_id="tenant-requester",
            file_hash="public_case::case-query",
            query="这份案例图谱讲了什么？",
            mode="local",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert payload["answer"] == "public case answer"
    assert payload["file_hash"] == "public_case::case-query"
    assert payload["graph_file_id"] == "public_case:case-query"
    assert payload["workspace_id"] == "ws_public"
    assert storage.graph_version_calls == [("tenant-public-source", "ver_public_1")]


def test_search_graph_recovers_public_case_legacy_workspace_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    registry_path = (tmp_path / "public_case_graphs.json").resolve()
    registry_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "case-query-legacy",
                    "display_name": "公共案例 Legacy Query",
                    "source_tenant_id": "tenant-public-source",
                    "source_file_hash": "hash-public-legacy",
                    "sort_order": 10,
                    "enabled": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODULE4_PUBLIC_CASE_REGISTRY_PATH", str(registry_path))

    backend_root = (tmp_path / "backend").resolve()
    current_workspace = (
        backend_root
        / "app"
        / "modules"
        / "module4"
        / "workspaces"
        / "default"
        / "batch-legacy"
        / "workspace-legacy"
    ).resolve()
    output_dir = (current_workspace / "output" / "snapshot-20260420").resolve()
    artifacts_dir = (output_dir / "artifacts").resolve()
    reports_dir = (output_dir / "reports").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "documents.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "text_units.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "entities.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "relationships.parquet").write_text("stub", encoding="utf-8")
    (current_workspace / "settings.yaml").write_text("encoding_model: cl100k_base\n", encoding="utf-8")
    manifest_path = (current_workspace / "workspace_manifest.json").resolve()
    manifest_path.write_text(
        json.dumps(
            {
                "workspace_dir": str(current_workspace),
                "latest_output_dir": str(output_dir),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    legacy_workspace = (
        backend_root / "module4" / "workspaces" / "default" / "batch-legacy" / "workspace-legacy"
    ).resolve()
    legacy_output_dir = (legacy_workspace / "output" / "snapshot-20260420").resolve()
    legacy_artifacts_dir = (legacy_output_dir / "artifacts").resolve()
    legacy_reports_dir = (legacy_output_dir / "reports").resolve()
    legacy_manifest_path = (legacy_workspace / "workspace_manifest.json").resolve()

    storage = _QueryStorage(
        graph_file={
            "graph_file_id": "gf_public_source_legacy",
            "tenant_id": "tenant-public-source",
            "file_hash": "hash-public-legacy",
            "file_name": "source-public-legacy.docx",
            "workspace_id": "ws_public_legacy",
            "active_version_id": "ver_public_legacy_1",
            "metadata": {
                "workspace_dir": str(legacy_workspace),
                "manifest_path": str(legacy_manifest_path),
                "output_dir": str(legacy_output_dir),
                "artifacts_dir": str(legacy_artifacts_dir),
                "reports_dir": str(legacy_reports_dir),
            },
        },
        graph_version={
            "tenant_id": "tenant-public-source",
            "graph_version_id": "ver_public_legacy_1",
            "workspace_id": "ws_public_legacy",
            "manifest_path": str(legacy_manifest_path),
            "output_dir": str(legacy_output_dir),
            "artifacts_dir": str(legacy_artifacts_dir),
            "reports_dir": str(legacy_reports_dir),
        },
    )

    monkeypatch.setattr(query_service, "_backend_root_dir", lambda: backend_root)

    captured_runtime: Dict[str, Any] = {}

    async def _fake_execute_query_runtime(*, runtime: Any, **_: Any) -> Dict[str, Any]:
        captured_runtime["workspace_dir"] = runtime.workspace_dir
        captured_runtime["artifacts_dir"] = runtime.artifacts_dir
        return {
            "answer": "public case legacy answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local",
        }

    async def _fake_canonicalize(**_: Any):
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "resolution_strategy": "storage_only",
            "used_fallback_candidates": False,
        }

    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setattr(
        query_service,
        "_canonicalize_linked_node_ids_with_storage_diagnostics",
        _fake_canonicalize,
    )

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = asyncio.run(
        query_service.search_graph(
            storage=storage,
            tenant_id="tenant-requester",
            file_hash="public_case::case-query-legacy",
            query="请概括这个公共案例图谱的核心内容",
            mode="local",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert payload["answer"] == "public case legacy answer"
    assert payload["file_hash"] == "public_case::case-query-legacy"
    assert payload["graph_file_id"] == "public_case:case-query-legacy"
    assert payload["workspace_id"] == "ws_public_legacy"
    assert captured_runtime["workspace_dir"] == current_workspace
    assert captured_runtime["artifacts_dir"] == artifacts_dir


def test_search_graph_recovers_public_case_workspace_by_file_hash_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    registry_path = (tmp_path / "public_case_graphs.json").resolve()
    registry_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "case-query-filehash",
                    "display_name": "公共案例 FileHash Query",
                    "source_tenant_id": "tenant-public-source",
                    "source_file_hash": "hash-public-filehash",
                    "sort_order": 10,
                    "enabled": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODULE4_PUBLIC_CASE_REGISTRY_PATH", str(registry_path))

    backend_root = (tmp_path / "backend").resolve()
    workspaces_root = (backend_root / "app" / "modules" / "module4" / "workspaces").resolve()
    current_workspace = (
        workspaces_root / "tenant-new" / "batch-new" / "workspace-new"
    ).resolve()
    output_dir = (current_workspace / "output" / "snapshot-20260420").resolve()
    artifacts_dir = (output_dir / "artifacts").resolve()
    reports_dir = (output_dir / "reports").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "documents.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "text_units.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "entities.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "relationships.parquet").write_text("stub", encoding="utf-8")
    (current_workspace / "settings.yaml").write_text("encoding_model: cl100k_base\n", encoding="utf-8")
    manifest_path = (current_workspace / "workspace_manifest.json").resolve()
    manifest_path.write_text(
        json.dumps(
            {
                "workspace_dir": str(current_workspace),
                "latest_output_dir": str(output_dir),
                "files": [
                    {
                        "file_hash": "hash-public-filehash",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    legacy_workspace = (
        backend_root / "module4" / "workspaces" / "tenant-old" / "batch-old" / "workspace-old"
    ).resolve()
    legacy_output_dir = (legacy_workspace / "output" / "snapshot-20260401").resolve()
    legacy_artifacts_dir = (legacy_output_dir / "artifacts").resolve()
    legacy_reports_dir = (legacy_output_dir / "reports").resolve()
    legacy_manifest_path = (legacy_workspace / "workspace_manifest.json").resolve()

    storage = _QueryStorage(
        graph_file={
            "graph_file_id": "gf_public_source_filehash",
            "tenant_id": "tenant-public-source",
            "file_hash": "hash-public-filehash",
            "file_name": "source-public-filehash.docx",
            "workspace_id": "ws_public_filehash",
            "active_version_id": "ver_public_filehash_1",
            "metadata": {
                "workspace_dir": str(legacy_workspace),
                "manifest_path": str(legacy_manifest_path),
                "output_dir": str(legacy_output_dir),
                "artifacts_dir": str(legacy_artifacts_dir),
                "reports_dir": str(legacy_reports_dir),
            },
        },
        graph_version={
            "tenant_id": "tenant-public-source",
            "graph_version_id": "ver_public_filehash_1",
            "workspace_id": "ws_public_filehash",
            "manifest_path": str(legacy_manifest_path),
            "output_dir": str(legacy_output_dir),
            "artifacts_dir": str(legacy_artifacts_dir),
            "reports_dir": str(legacy_reports_dir),
        },
    )

    monkeypatch.setattr(query_service, "_backend_root_dir", lambda: backend_root)

    captured_runtime: Dict[str, Any] = {}

    async def _fake_execute_query_runtime(*, runtime: Any, **_: Any) -> Dict[str, Any]:
        captured_runtime["workspace_dir"] = runtime.workspace_dir
        captured_runtime["artifacts_dir"] = runtime.artifacts_dir
        return {
            "answer": "public case filehash answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local",
        }

    async def _fake_canonicalize(**_: Any):
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "resolution_strategy": "storage_only",
            "used_fallback_candidates": False,
        }

    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setattr(
        query_service,
        "_canonicalize_linked_node_ids_with_storage_diagnostics",
        _fake_canonicalize,
    )

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = asyncio.run(
        query_service.search_graph(
            storage=storage,
            tenant_id="tenant-requester",
            file_hash="public_case::case-query-filehash",
            query="请概括这个公共案例图谱的核心内容",
            mode="local",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert payload["answer"] == "public case filehash answer"
    assert payload["file_hash"] == "public_case::case-query-filehash"
    assert payload["graph_file_id"] == "public_case:case-query-filehash"
    assert payload["workspace_id"] == "ws_public_filehash"
    assert captured_runtime["workspace_dir"] == current_workspace
    assert captured_runtime["artifacts_dir"] == artifacts_dir


def test_locate_workspace_by_file_hash_skips_output_subtrees(
    monkeypatch,
    tmp_path: Path,
) -> None:
    backend_root = (tmp_path / "backend").resolve()
    workspaces_root = (backend_root / "app" / "modules" / "module4" / "workspaces").resolve()
    workspace_dir = (workspaces_root / "tenant-a" / "batch-a" / "workspace-a").resolve()
    output_dir = (workspace_dir / "output" / "snapshot-20260420").resolve()
    artifacts_dir = (output_dir / "artifacts").resolve()
    reports_dir = (output_dir / "reports").resolve()
    lancedb_dir = (output_dir / "lancedb" / "community_full_content.lance" / "_indices").resolve()

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    lancedb_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "documents.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "text_units.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "entities.parquet").write_text("stub", encoding="utf-8")
    (artifacts_dir / "relationships.parquet").write_text("stub", encoding="utf-8")
    (workspace_dir / "settings.yaml").write_text("encoding_model: cl100k_base\n", encoding="utf-8")
    (workspace_dir / "workspace_manifest.json").write_text(
        json.dumps(
            {
                "workspace_dir": str(workspace_dir),
                "latest_output_dir": str(output_dir),
                "files": [{"file_hash": "hash-scan-safe"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    visited_roots: list[Path] = []
    real_walk = query_service.os.walk

    def _tracking_walk(*args: Any, **kwargs: Any):
        for current_root, dir_names, file_names in real_walk(*args, **kwargs):
            visited_roots.append(Path(current_root).resolve())
            yield current_root, dir_names, file_names

    monkeypatch.setattr(query_service, "_backend_root_dir", lambda: backend_root)
    monkeypatch.setattr(query_service.os, "walk", _tracking_walk)

    located = query_service._locate_workspace_by_file_hash("hash-scan-safe")

    assert located == (workspace_dir, artifacts_dir)
    assert workspace_dir in visited_roots
    assert output_dir not in visited_roots
    assert not any(output_dir in path.parents for path in visited_roots)


def test_subprocess_query_entry_builds_runtime_with_required_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace_dir = (tmp_path / "workspace").resolve()
    artifacts_dir = (workspace_dir / "output" / "snapshot" / "artifacts").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "settings.yaml").write_text("encoding_model: cl100k_base\n", encoding="utf-8")

    captured_runtime: Dict[str, Any] = {}

    async def _fake_execute_query_runtime(*, runtime: Any, **_: Any) -> Dict[str, Any]:
        captured_runtime["response_graph_file"] = runtime.response_graph_file
        captured_runtime["storage_tenant_id"] = runtime.storage_tenant_id
        captured_runtime["requested_file_hash"] = runtime.requested_file_hash
        return {
            "answer": "subprocess answer",
            "mode": "basic",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:basic",
        }

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = query_service._subprocess_query_entry(
        json.dumps(
            {
                "workspace_dir": str(workspace_dir),
                "artifacts_dir": str(artifacts_dir),
                "mode": "basic",
                "query": "请概括案例内容",
                "response_type": "multiple paragraphs",
                "community_level": 2,
                "dynamic_community_selection": False,
                "verbose": False,
            },
            ensure_ascii=False,
        )
    )

    assert payload["answer"] == "subprocess answer"
    assert payload["mode"] == "basic"
    assert captured_runtime["response_graph_file"] == {}
    assert captured_runtime["storage_tenant_id"] == ""
    assert captured_runtime["requested_file_hash"] == ""


def test_search_graph_prefers_subprocess_for_public_case_when_query_python_differs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MODULE4_GRAPHRAG_QUERY_EXECUTION_MODE", raising=False)
    runtime = query_service.GraphRAGResolvedRuntime(
        graph_file={"graph_file_id": "gf_source"},
        response_graph_file={"graph_file_id": "public_case:case-query"},
        graph_version={"graph_version_id": "ver_public_1", "workspace_id": "ws_public"},
        workspace_dir=(tmp_path / "workspace").resolve(),
        artifacts_dir=(tmp_path / "workspace" / "output" / "snapshot" / "artifacts").resolve(),
        storage_tenant_id="tenant-public-source",
        requested_file_hash="public_case::case-query",
    )

    async def _fake_resolve_runtime(**_: Any):
        return runtime

    monkeypatch.setattr(query_service, "_resolve_runtime", _fake_resolve_runtime)
    monkeypatch.setattr(query_service, "_resolve_query_python_bin", lambda: "D:/py311/python.exe")

    captured: Dict[str, Any] = {"in_process_calls": 0, "subprocess_calls": 0}

    async def _fake_execute_query_runtime_via_subprocess(**_: Any) -> Dict[str, Any]:
        captured["subprocess_calls"] += 1
        return {
            "answer": "public case subprocess answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local:subprocess",
        }

    async def _fake_execute_query_runtime(**_: Any) -> Dict[str, Any]:
        captured["in_process_calls"] += 1
        return {
            "answer": "public case in-process answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local",
        }

    async def _fake_canonicalize(**_: Any):
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "resolution_strategy": "storage_only",
            "used_fallback_candidates": False,
        }

    monkeypatch.setattr(query_service, "_execute_query_runtime_via_subprocess", _fake_execute_query_runtime_via_subprocess)
    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setattr(
        query_service,
        "_canonicalize_linked_node_ids_with_storage_diagnostics",
        _fake_canonicalize,
    )

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = asyncio.run(
        query_service.search_graph(
            storage=object(),
            tenant_id="tenant-requester",
            file_hash="public_case::case-query",
            query="请概括这份公共案例图谱的核心内容。",
            mode="local",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert payload["answer"] == "public case subprocess answer"
    assert payload["graph_file_id"] == "public_case:case-query"
    assert payload["workspace_id"] == "ws_public"
    assert captured["subprocess_calls"] == 1
    assert captured["in_process_calls"] == 0


def test_search_graph_keeps_in_process_for_private_graphs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime = query_service.GraphRAGResolvedRuntime(
        graph_file={"graph_file_id": "gf_private"},
        response_graph_file={"graph_file_id": "gf_private"},
        graph_version={"graph_version_id": "ver_private_1", "workspace_id": "ws_private"},
        workspace_dir=(tmp_path / "workspace").resolve(),
        artifacts_dir=(tmp_path / "workspace" / "output" / "snapshot" / "artifacts").resolve(),
        storage_tenant_id="tenant-private",
        requested_file_hash="hash-private",
    )

    async def _fake_resolve_runtime(**_: Any):
        return runtime

    monkeypatch.setattr(query_service, "_resolve_runtime", _fake_resolve_runtime)
    monkeypatch.setattr(query_service, "_resolve_query_python_bin", lambda: "D:/py311/python.exe")

    captured: Dict[str, Any] = {"in_process_calls": 0, "subprocess_calls": 0}

    async def _fake_execute_query_runtime_via_subprocess(**_: Any) -> Dict[str, Any]:
        captured["subprocess_calls"] += 1
        return {
            "answer": "private subprocess answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local:subprocess",
        }

    async def _fake_execute_query_runtime(**_: Any) -> Dict[str, Any]:
        captured["in_process_calls"] += 1
        return {
            "answer": "private in-process answer",
            "mode": "local",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [],
            },
            "source": "graphrag:query:local",
        }

    async def _fake_canonicalize(**_: Any):
        return [], {
            "candidate_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_candidates": [],
            "resolution_strategy": "storage_only",
            "used_fallback_candidates": False,
        }

    monkeypatch.setattr(query_service, "_execute_query_runtime_via_subprocess", _fake_execute_query_runtime_via_subprocess)
    monkeypatch.setattr(query_service, "_execute_query_runtime", _fake_execute_query_runtime)
    monkeypatch.setattr(
        query_service,
        "_canonicalize_linked_node_ids_with_storage_diagnostics",
        _fake_canonicalize,
    )

    fake_graphrag_module = types.ModuleType("graphrag")
    fake_graphrag_api_module = types.ModuleType("graphrag.api")
    fake_graphrag_utils_module = types.ModuleType("graphrag.utils")
    fake_graphrag_utils_api_module = types.ModuleType("graphrag.utils.api")
    fake_graphrag_utils_api_module.reformat_context_data = lambda value: value

    monkeypatch.setitem(sys.modules, "graphrag", fake_graphrag_module)
    monkeypatch.setitem(sys.modules, "graphrag.api", fake_graphrag_api_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils", fake_graphrag_utils_module)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", fake_graphrag_utils_api_module)

    payload = asyncio.run(
        query_service.search_graph(
            storage=object(),
            tenant_id="tenant-private",
            file_hash="hash-private",
            query="请概括这份私有图谱的核心内容。",
            mode="local",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert payload["answer"] == "private in-process answer"
    assert payload["graph_file_id"] == "gf_private"
    assert payload["workspace_id"] == "ws_private"
    assert captured["in_process_calls"] == 1
    assert captured["subprocess_calls"] == 0
