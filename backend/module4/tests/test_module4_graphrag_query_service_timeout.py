from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from typing import Any, Dict

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag import query_service


def _install_fake_graphrag_modules(
    *,
    monkeypatch: Any,
    drift_search: Any,
    local_search: Any,
    basic_search: Any,
    global_search: Any,
) -> None:
    graphrag_pkg = types.ModuleType("graphrag")
    graphrag_api = types.ModuleType("graphrag.api")
    graphrag_utils_pkg = types.ModuleType("graphrag.utils")
    graphrag_utils_api = types.ModuleType("graphrag.utils.api")

    graphrag_api.drift_search = drift_search
    graphrag_api.local_search = local_search
    graphrag_api.basic_search = basic_search
    graphrag_api.global_search = global_search
    graphrag_utils_api.reformat_context_data = lambda raw: raw

    monkeypatch.setitem(sys.modules, "graphrag", graphrag_pkg)
    monkeypatch.setitem(sys.modules, "graphrag.api", graphrag_api)
    monkeypatch.setitem(sys.modules, "graphrag.utils", graphrag_utils_pkg)
    monkeypatch.setitem(sys.modules, "graphrag.utils.api", graphrag_utils_api)


def _fake_runtime(tmp_path: Path) -> query_service.GraphRAGResolvedRuntime:
    workspace_dir = tmp_path / "workspace"
    artifacts_dir = workspace_dir / "output" / "demo" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return query_service.GraphRAGResolvedRuntime(
        graph_file={
            "file_hash": "hash-1",
            "graph_file_id": "graph-file-1",
            "workspace_id": "workspace-1",
        },
        graph_version={
            "graph_version_id": "graph-version-1",
            "workspace_id": "workspace-1",
        },
        workspace_dir=workspace_dir,
        artifacts_dir=artifacts_dir,
    )


def _install_runtime_stubs(monkeypatch: Any, tmp_path: Path) -> None:
    runtime = _fake_runtime(tmp_path)

    async def fake_resolve_runtime(*, storage: Any, tenant_id: str, file_hash: str) -> query_service.GraphRAGResolvedRuntime:
        return runtime

    async def fake_load_output_frames(
        *,
        runtime: query_service.GraphRAGResolvedRuntime,
        required: Any,
        optional: Any = (),
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        frame_names = list(required) + list(optional)
        return {"fake_config": True}, {name: [] for name in frame_names}

    monkeypatch.setattr(query_service, "_resolve_runtime", fake_resolve_runtime)
    monkeypatch.setattr(query_service, "_load_output_frames", fake_load_output_frames)


def test_drift_timeout_falls_back_to_local(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_DRIFT_SEC", "0.01")
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_LOCAL_SEC", "2")
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_BASIC_SEC", "2")

    async def drift_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        await asyncio.sleep(0.05)
        return "drift-answer", {}

    async def local_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        return "local-answer", {
            "entities": [{"id": "ent-1"}],
            "reports": [],
            "relationships": [],
            "claims": [],
            "sources": [],
        }

    async def basic_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        raise AssertionError("basic_search should not be used when local fallback succeeds")

    async def global_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        return "global-answer", {}

    _install_fake_graphrag_modules(
        monkeypatch=monkeypatch,
        drift_search=drift_search,
        local_search=local_search,
        basic_search=basic_search,
        global_search=global_search,
    )
    _install_runtime_stubs(monkeypatch, tmp_path)

    result = asyncio.run(
        query_service.search_graph(
            storage=object(),
            tenant_id="tenant-a",
            file_hash="hash-a",
            query="卫生",
            mode="drift",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert result["mode"] == "local"
    assert result["source"] == "graphrag:query:drift:fallback:local"
    assert result["answer"] == "local-answer"


def test_drift_timeout_falls_back_to_basic_when_local_unavailable(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_DRIFT_SEC", "0.01")
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_LOCAL_SEC", "0.05")
    monkeypatch.setenv("MODULE4_GRAPHRAG_QUERY_TIMEOUT_BASIC_SEC", "2")

    async def drift_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        await asyncio.sleep(0.05)
        return "drift-answer", {}

    async def local_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        raise RuntimeError("local mode unavailable")

    async def basic_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        return "basic-answer", {
            "entities": [],
            "reports": [],
            "relationships": [],
            "claims": [],
            "sources": [{"id": "chunk-1", "text": "卫生"}],
        }

    async def global_search(**kwargs: Any) -> tuple[str, Dict[str, Any]]:
        return "global-answer", {}

    _install_fake_graphrag_modules(
        monkeypatch=monkeypatch,
        drift_search=drift_search,
        local_search=local_search,
        basic_search=basic_search,
        global_search=global_search,
    )
    _install_runtime_stubs(monkeypatch, tmp_path)

    result = asyncio.run(
        query_service.search_graph(
            storage=object(),
            tenant_id="tenant-a",
            file_hash="hash-a",
            query="卫生",
            mode="drift",
            response_type="multiple paragraphs",
            community_level=2,
            dynamic_community_selection=False,
            verbose=False,
        )
    )

    assert result["mode"] == "basic"
    assert result["source"] == "graphrag:query:drift:fallback:basic"
    assert result["answer"] == "basic-answer"
