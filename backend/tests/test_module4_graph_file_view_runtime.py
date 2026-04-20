from __future__ import annotations

import asyncio
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


query_runtime = import_module("app.modules.module4.services.query.runtime")


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _build_helpers(*, resolve_artifact_local_path=None, register_file_asset=None):
    return query_runtime.Module4QueryRuntimeHelpers(
        default_tenant=lambda: "default",
        risk_key=lambda seed: f"rk-{abs(hash(seed))}",
        to_float=_to_float,
        to_int=_to_int,
        as_dict=_as_dict,
        as_list=_as_list,
        artifact_summary_snippet=lambda **kwargs: str(kwargs.get("raw_snippet") or "").strip(),
        normalize_artifact_attrs_for_response=lambda _node_type, attrs: dict(attrs),
        artifact_display_name_from_attrs=lambda display_name, **_kwargs: display_name,
        edge_direction={"out", "bi"},
        alert_severity={"yellow", "orange", "red"},
        alert_status={"open", "ack", "resolved", "false_positive"},
        rule_kind={"deterministic"},
        resolve_artifact_local_path=resolve_artifact_local_path,
        register_file_asset=register_file_asset,
    )


class _GraphFileStorage:
    def __init__(self, *, graph_file: Dict[str, Any], nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
        self._graph_file = dict(graph_file)
        self._nodes = [dict(row) for row in nodes]
        self._edges = [dict(row) for row in edges]

    async def get_graph_file(self, *, tenant_id: str, file_hash: str) -> Dict[str, Any] | None:
        if tenant_id != str(self._graph_file.get("tenant_id") or ""):
            return None
        if file_hash != str(self._graph_file.get("file_hash") or ""):
            return None
        return dict(self._graph_file)

    async def list_nodes_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        node_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, limit
        if graph_file_id != str(self._graph_file.get("graph_file_id") or ""):
            return []
        allowed = {str(item).strip() for item in node_types if str(item).strip()}
        if not allowed:
            return [dict(row) for row in self._nodes]
        return [dict(row) for row in self._nodes if str(row.get("node_type") or "") in allowed]

    async def list_edges_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        relation_types: List[str],
        node_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, limit
        if graph_file_id != str(self._graph_file.get("graph_file_id") or ""):
            return []
        allowed_relations = {str(item).strip() for item in relation_types if str(item).strip()}
        allowed_nodes = {str(item).strip() for item in node_ids if str(item).strip()}
        rows = [
            dict(row)
            for row in self._edges
            if str(row.get("source_node_id") or "") in allowed_nodes
            and str(row.get("target_node_id") or "") in allowed_nodes
        ]
        if not allowed_relations:
            return rows
        return [row for row in rows if str(row.get("relation_type") or "") in allowed_relations]


def test_graph_file_view_response_falls_back_to_db_graph_when_artifacts_missing(monkeypatch) -> None:
    monkeypatch.setattr(query_runtime, "load_artifact_graph_snapshot", lambda _graph_file: None)
    storage = _GraphFileStorage(
        graph_file={
            "graph_file_id": "gf_1",
            "tenant_id": "tenant-a",
            "file_hash": "hash_1",
            "file_name": "demo.docx",
            "workspace_id": "ws_1",
        },
        nodes=[
            {
                "node_id": "doc_1",
                "node_type": "Document",
                "canonical_key": "hash_1",
                "display_name": "demo",
                "confidence": 1.0,
                "attrs": {"file_hash": "hash_1"},
                "updated_at": None,
            },
            {
                "node_id": "entity_1",
                "node_type": "Entity",
                "canonical_key": "entity-1",
                "display_name": "南京市",
                "confidence": 0.94,
                "attrs": {"entity_type": "city"},
                "updated_at": None,
            },
        ],
        edges=[
            {
                "edge_id": "edge_1",
                "source_node_id": "doc_1",
                "target_node_id": "entity_1",
                "relation_type": "mentions",
                "direction": "out",
                "confidence": 0.9,
                "risk_score": 0.0,
                "attrs": {},
                "updated_at": None,
            }
        ],
    )

    response = asyncio.run(
        query_runtime.graph_file_view_response(
            storage=storage,
            helpers=_build_helpers(),
            tenant_id="tenant-a",
            file_hash="hash_1",
            node_types=[],
            relation_types=[],
            limit_nodes=50,
            limit_edges=50,
        )
    )

    assert response.source == "module4:db:file_scope"
    assert response.workspace_id == "ws_1"
    assert response.stats.node_count == 2
    assert response.stats.edge_count == 1
    assert {node.node_id for node in response.nodes} == {"doc_1", "entity_1"}
    assert response.edges[0].relation_type == "mentions"


def test_graph_file_view_response_augments_node_artifact_links_in_db_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(query_runtime, "load_artifact_graph_snapshot", lambda _graph_file: None)

    artifact = (tmp_path / "module2" / "artifacts" / "figures" / "demo.png").resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"fake-png")

    register_calls: Dict[str, Any] = {}

    def _resolve(reference: str) -> Path | None:
        if reference == "/extract/artifact/figures/demo.png":
            return artifact
        return None

    def _register(**kwargs) -> Dict[str, Any]:
        register_calls.update(kwargs)
        return {"file_id": "fa_demo_png"}

    storage = _GraphFileStorage(
        graph_file={
            "graph_file_id": "gf_1",
            "tenant_id": "tenant-a",
            "file_hash": "hash_1",
            "file_name": "demo.docx",
            "workspace_id": "ws_1",
        },
        nodes=[
            {
                "node_id": "figure_1",
                "node_type": "Figure",
                "canonical_key": "figure-1",
                "display_name": "图 1",
                "confidence": 0.98,
                "attrs": {
                    "artifact_url": "/extract/artifact/figures/demo.png",
                    "caption": "示意图",
                },
                "updated_at": None,
            }
        ],
        edges=[],
    )

    response = asyncio.run(
        query_runtime.graph_file_view_response(
            storage=storage,
            helpers=_build_helpers(
                resolve_artifact_local_path=_resolve,
                register_file_asset=_register,
            ),
            tenant_id="tenant-a",
            file_hash="hash_1",
            node_types=[],
            relation_types=[],
            limit_nodes=50,
            limit_edges=50,
        )
    )

    assert response.source == "module4:db:file_scope"
    assert response.stats.node_count == 1
    node = response.nodes[0]
    assert node.attrs["artifact_file_id"] == "fa_demo_png"
    assert node.attrs["artifact_download_url"] == "/download/fa_demo_png"
    assert str(register_calls.get("owner_id")) == "tenant-a"
    assert Path(str(register_calls.get("path"))).resolve() == artifact


class _PublicCaseStorage:
    def __init__(
        self,
        *,
        private_rows: List[Dict[str, Any]],
        source_rows: List[Dict[str, Any]],
        nodes_by_graph_file_id: Dict[str, List[Dict[str, Any]]],
        edges_by_graph_file_id: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        self._private_rows = [dict(row) for row in private_rows]
        self._source_rows = [dict(row) for row in source_rows]
        self._rows_by_key = {
            (str(row.get("tenant_id") or ""), str(row.get("file_hash") or "")): dict(row)
            for row in [*self._private_rows, *self._source_rows]
        }
        self._nodes_by_graph_file_id = {
            key: [dict(item) for item in value] for key, value in nodes_by_graph_file_id.items()
        }
        self._edges_by_graph_file_id = {
            key: [dict(item) for item in value] for key, value in edges_by_graph_file_id.items()
        }

    async def list_graph_files(self, *, tenant_id: str, status: str | None, limit: int) -> List[Dict[str, Any]]:
        rows = [dict(row) for row in self._private_rows if str(row.get("tenant_id") or "") == tenant_id]
        if status:
            rows = [row for row in rows if str(row.get("status") or "").strip() == str(status).strip()]
        return rows[:limit]

    async def get_graph_file(self, *, tenant_id: str, file_hash: str) -> Dict[str, Any] | None:
        row = self._rows_by_key.get((tenant_id, file_hash))
        return dict(row) if row else None

    async def list_nodes_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        node_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, limit
        rows = [dict(item) for item in self._nodes_by_graph_file_id.get(graph_file_id, [])]
        allowed = {str(item).strip() for item in node_types if str(item).strip()}
        if not allowed:
            return rows
        return [row for row in rows if str(row.get("node_type") or "") in allowed]

    async def list_edges_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        relation_types: List[str],
        node_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, limit
        rows = [dict(item) for item in self._edges_by_graph_file_id.get(graph_file_id, [])]
        allowed_relations = {str(item).strip() for item in relation_types if str(item).strip()}
        allowed_nodes = {str(item).strip() for item in node_ids if str(item).strip()}
        filtered = [
            row
            for row in rows
            if str(row.get("source_node_id") or "") in allowed_nodes
            and str(row.get("target_node_id") or "") in allowed_nodes
        ]
        if not allowed_relations:
            return filtered
        return [row for row in filtered if str(row.get("relation_type") or "") in allowed_relations]


def test_list_graph_files_response_appends_public_case_rows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(query_runtime, "load_artifact_graph_snapshot", lambda _graph_file: None)

    registry_path = (tmp_path / "public_case_graphs.json").resolve()
    registry_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "case-one",
                    "display_name": "案例图谱·统计公报（DOCX）",
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

    storage = _PublicCaseStorage(
        private_rows=[
            {
                "graph_file_id": "gf_private",
                "tenant_id": "tenant-a",
                "file_hash": "hash-private",
                "file_name": "private.docx",
                "workspace_id": "ws_private",
                "status": "ready",
                "node_count": 3,
                "edge_count": 2,
                "metadata": {},
            }
        ],
        source_rows=[
            {
                "graph_file_id": "gf_public_source",
                "tenant_id": "tenant-public-source",
                "file_hash": "hash-public",
                "file_name": "source-public.docx",
                "workspace_id": "ws_public",
                "status": "ready",
                "node_count": 6,
                "edge_count": 5,
                "metadata": {},
            }
        ],
        nodes_by_graph_file_id={},
        edges_by_graph_file_id={},
    )

    response = asyncio.run(
        query_runtime.list_graph_files_response(
            storage=storage,
            helpers=_build_helpers(),
            tenant_id="tenant-a",
            status="ready",
            limit=50,
        )
    )

    file_hashes = {item.file_hash for item in response.items}
    assert "hash-private" in file_hashes
    assert "public_case::case-one" in file_hashes

    public_item = next(item for item in response.items if item.file_hash == "public_case::case-one")
    assert public_item.graph_file_id == "public_case:case-one"
    assert public_item.tenant_id == "public_case_library"
    assert public_item.metadata["visibility"] == "public_case"
    assert public_item.metadata["public_case"]["source_file_hash"] == "hash-public"


def test_graph_file_view_response_reads_public_case_via_source_tenant(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(query_runtime, "load_artifact_graph_snapshot", lambda _graph_file: None)

    registry_path = (tmp_path / "public_case_graphs.json").resolve()
    registry_path.write_text(
        json.dumps(
            [
                {
                    "case_id": "case-two",
                    "display_name": "案例图谱·合肥公报（TXT）",
                    "source_tenant_id": "tenant-public-source",
                    "source_file_hash": "hash-public",
                    "sort_order": 20,
                    "enabled": True,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODULE4_PUBLIC_CASE_REGISTRY_PATH", str(registry_path))

    storage = _PublicCaseStorage(
        private_rows=[],
        source_rows=[
            {
                "graph_file_id": "gf_public_source",
                "tenant_id": "tenant-public-source",
                "file_hash": "hash-public",
                "file_name": "source-public.txt",
                "workspace_id": "ws_public",
                "status": "ready",
                "node_count": 2,
                "edge_count": 1,
                "metadata": {},
            }
        ],
        nodes_by_graph_file_id={
            "gf_public_source": [
                {
                    "node_id": "entity_1",
                    "node_type": "Entity",
                    "canonical_key": "entity-1",
                    "display_name": "合肥市",
                    "confidence": 0.97,
                    "attrs": {"entity_type": "city"},
                    "updated_at": None,
                },
                {
                    "node_id": "entity_2",
                    "node_type": "Entity",
                    "canonical_key": "entity-2",
                    "display_name": "统计公报",
                    "confidence": 0.96,
                    "attrs": {"entity_type": "report"},
                    "updated_at": None,
                },
            ]
        },
        edges_by_graph_file_id={
            "gf_public_source": [
                {
                    "edge_id": "edge_1",
                    "source_node_id": "entity_1",
                    "target_node_id": "entity_2",
                    "relation_type": "related_to",
                    "direction": "out",
                    "confidence": 0.88,
                    "risk_score": 0.0,
                    "attrs": {},
                    "updated_at": None,
                }
            ]
        },
    )

    response = asyncio.run(
        query_runtime.graph_file_view_response(
            storage=storage,
            helpers=_build_helpers(),
            tenant_id="tenant-requester",
            file_hash="public_case::case-two",
            node_types=[],
            relation_types=[],
            limit_nodes=50,
            limit_edges=50,
        )
    )

    assert response.source == "module4:db:file_scope"
    assert response.workspace_id == "ws_public"
    assert response.stats.node_count == 2
    assert response.stats.edge_count == 1
    assert {node.display_name for node in response.nodes} == {"合肥市", "统计公报"}
