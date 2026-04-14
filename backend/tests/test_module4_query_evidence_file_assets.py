from __future__ import annotations

import asyncio
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


def _build_helpers(
    *,
    resolve_artifact_local_path,
    register_file_asset,
):
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


class _EvidenceStorage:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows

    async def list_evidence(
        self,
        *,
        tenant_id: str,
        doc_id: str | None,
        object_type: str | None,
        object_id: str | None,
        page: int,
        page_size: int,
    ) -> tuple[int, List[Dict[str, Any]]]:
        del tenant_id, doc_id, object_type, object_id, page, page_size
        return len(self._rows), list(self._rows)


class _GraphStorage:
    def __init__(self, *, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
        self._nodes = nodes
        self._edges = edges

    async def list_graph_files(
        self,
        *,
        tenant_id: str,
        status: str | None,
        limit: int,
    ) -> List[Dict[str, Any]]:
        del status, limit
        return [
            {
                "graph_file_id": "gf_1",
                "tenant_id": tenant_id,
                "file_hash": "hash_1",
                "file_name": "demo.docx",
                "workspace_id": "ws_1",
                "status": "ready",
                "metadata": {},
            }
        ]

    async def list_nodes_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        node_types: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, graph_file_id, node_types, limit
        return [dict(row) for row in self._nodes]

    async def list_edges_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        relation_types: List[str],
        node_ids: List[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        del tenant_id, graph_file_id, relation_types, limit
        allow = set(node_ids)
        return [
            dict(row)
            for row in self._edges
            if str(row.get("source_node_id") or "") in allow and str(row.get("target_node_id") or "") in allow
        ]


def test_module4_evidence_response_augments_artifact_file_links(tmp_path: Path) -> None:
    artifact = (tmp_path / "module2" / "artifacts" / "trace" / "demo.txt").resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("demo", encoding="utf-8")

    captured: Dict[str, Any] = {}

    def _resolve(reference: str) -> Path | None:
        return artifact if reference == "/extract/artifact/trace/demo.txt" else None

    def _register(**kwargs) -> Dict[str, Any]:
        captured.update(kwargs)
        return {"file_id": "fa_demo"}

    helpers = _build_helpers(
        resolve_artifact_local_path=_resolve,
        register_file_asset=_register,
    )
    storage = _EvidenceStorage(
        rows=[
            {
                "evidence_id": "ev_1",
                "doc_id": "doc_1",
                "object_type": "chunk",
                "object_id": "chunk_1",
                "ref_id": "ref_1",
                "page_no": 1,
                "snippet": "snippet",
                "locator": {},
                "bbox": [],
                "artifact_url": "/extract/artifact/trace/demo.txt",
                "confidence": 0.9,
                "created_at": None,
            }
        ]
    )

    response = asyncio.run(
        query_runtime.evidence_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-a",
            doc_id=None,
            object_type=None,
            object_id=None,
            page=1,
            page_size=20,
        )
    )

    assert response.total == 1
    assert response.items[0].artifact_file_id == "fa_demo"
    assert response.items[0].artifact_download_url == "/download/fa_demo"
    assert str(captured.get("owner_id")) == "tenant-a"
    assert Path(str(captured.get("path"))).resolve() == artifact


def test_module4_evidence_response_reuses_asset_cache_for_duplicate_artifact(tmp_path: Path) -> None:
    artifact = (tmp_path / "module2" / "artifacts" / "trace" / "dup.txt").resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("dup", encoding="utf-8")

    register_calls = {"count": 0}

    def _resolve(reference: str) -> Path | None:
        return artifact if reference == "/extract/artifact/trace/dup.txt" else None

    def _register(**_kwargs) -> Dict[str, Any]:
        register_calls["count"] += 1
        return {"file_id": "fa_dup"}

    helpers = _build_helpers(
        resolve_artifact_local_path=_resolve,
        register_file_asset=_register,
    )
    storage = _EvidenceStorage(
        rows=[
            {
                "evidence_id": "ev_1",
                "doc_id": "doc_1",
                "object_type": "chunk",
                "object_id": "chunk_1",
                "ref_id": "ref_1",
                "page_no": 1,
                "snippet": "snippet-1",
                "locator": {},
                "bbox": [],
                "artifact_url": "/extract/artifact/trace/dup.txt",
                "confidence": 0.9,
                "created_at": None,
            },
            {
                "evidence_id": "ev_2",
                "doc_id": "doc_1",
                "object_type": "chunk",
                "object_id": "chunk_2",
                "ref_id": "ref_2",
                "page_no": 1,
                "snippet": "snippet-2",
                "locator": {},
                "bbox": [],
                "artifact_url": "/extract/artifact/trace/dup.txt",
                "confidence": 0.85,
                "created_at": None,
            },
        ]
    )

    response = asyncio.run(
        query_runtime.evidence_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-a",
            doc_id=None,
            object_type=None,
            object_id=None,
            page=1,
            page_size=20,
        )
    )

    assert response.total == 2
    assert all(item.artifact_file_id == "fa_dup" for item in response.items)
    assert register_calls["count"] == 1


def test_module4_query_payload_augments_context_data_file_links(tmp_path: Path) -> None:
    preview_pdf = (tmp_path / "module2" / "artifacts" / "preview" / "op" / "demo.pdf").resolve()
    preview_pdf.parent.mkdir(parents=True, exist_ok=True)
    preview_pdf.write_bytes(b"%PDF-1.4")
    assistant_json = (tmp_path / "module2" / "artifacts" / "assistant_payload" / "demo.json").resolve()
    assistant_json.parent.mkdir(parents=True, exist_ok=True)
    assistant_json.write_text('{"ok": true}', encoding="utf-8")

    def _resolve(reference: str) -> Path | None:
        mapping = {
            "/extract/artifact/preview/op/demo.pdf": preview_pdf,
            "assistant_payload/demo.json": assistant_json,
        }
        return mapping.get(reference)

    def _register(**kwargs) -> Dict[str, Any]:
        filename = str(kwargs.get("filename") or "")
        if filename.endswith(".pdf"):
            return {"file_id": "fa_pdf"}
        return {"file_id": "fa_json"}

    helpers = _build_helpers(
        resolve_artifact_local_path=_resolve,
        register_file_asset=_register,
    )

    payload = {
        "answer": "ok",
        "mode": "local",
        "query": "demo",
        "response_type": "multiple paragraphs",
        "file_hash": "hash_1",
        "context_data": {
            "sources": [
                {
                    "id": "src_1",
                    "artifact_url": "/extract/artifact/preview/op/demo.pdf",
                }
            ],
            "reports": [
                {
                    "id": "rep_1",
                    "assistant_payload_artifact_path": "assistant_payload/demo.json",
                }
            ],
        },
    }

    updated = query_runtime.augment_graphrag_query_payload_with_file_assets(
        helpers=helpers,
        payload=payload,
        tenant_id="tenant-a",
    )

    source_row = updated["context_data"]["sources"][0]
    report_row = updated["context_data"]["reports"][0]
    assert source_row["artifact_file_id"] == "fa_pdf"
    assert source_row["artifact_download_url"] == "/download/fa_pdf"
    assert report_row["assistant_payload_artifact_file_id"] == "fa_json"
    assert report_row["assistant_payload_artifact_download_url"] == "/download/fa_json"


def test_module4_graph_response_augments_node_attrs_file_links(tmp_path: Path) -> None:
    node_artifact = (tmp_path / "module2" / "artifacts" / "preview" / "op" / "node.pdf").resolve()
    node_artifact.parent.mkdir(parents=True, exist_ok=True)
    node_artifact.write_bytes(b"%PDF-1.4")

    register_calls = {"count": 0}

    def _resolve(reference: str) -> Path | None:
        if reference == "/extract/artifact/preview/op/node.pdf":
            return node_artifact
        return None

    def _register(**_kwargs) -> Dict[str, Any]:
        register_calls["count"] += 1
        return {"file_id": "fa_node"}

    helpers = _build_helpers(
        resolve_artifact_local_path=_resolve,
        register_file_asset=_register,
    )
    storage = _GraphStorage(
        nodes=[
            {
                "node_id": "n1",
                "node_type": "entity",
                "canonical_key": "n1",
                "display_name": "节点一",
                "confidence": 0.9,
                "attrs": {
                    "artifact_url": "/extract/artifact/preview/op/node.pdf",
                },
                "updated_at": None,
            }
        ],
        edges=[
            {
                "edge_id": "e1",
                "source_node_id": "n1",
                "target_node_id": "n1",
                "relation_type": "related_to",
                "direction": "out",
                "confidence": 0.8,
                "risk_score": 0.0,
                "attrs": {},
                "updated_at": None,
            }
        ],
    )

    response = asyncio.run(
        query_runtime.graph_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-a",
            node_types=[],
            relation_types=[],
            limit_nodes=100,
            limit_edges=200,
        )
    )

    assert response.nodes
    attrs = response.nodes[0].attrs
    assert attrs["artifact_file_id"] == "fa_node"
    assert attrs["artifact_download_url"] == "/download/fa_node"
    assert register_calls["count"] == 1
