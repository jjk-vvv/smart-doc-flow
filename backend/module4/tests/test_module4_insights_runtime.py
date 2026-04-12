from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from fastapi import HTTPException

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.schemas import ExplainRequest  # noqa: E402
from app.services.insights.runtime import (  # noqa: E402
    Module4InsightRuntimeHelpers,
    explain_response,
)


class _NoopStorage:
    async def get_alert(self, alert_id: str, *, tenant_id: str) -> Dict[str, Any] | None:
        return None


def _build_helpers(
    *,
    load_artifact_neighborhood,
    load_evidence_for_node,
) -> Module4InsightRuntimeHelpers:
    def _as_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return []

    def _normalize_graph_node_row(row: Dict[str, Any]) -> Dict[str, Any]:
        attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
        return {
            "node_id": str(row.get("node_id") or ""),
            "node_type": str(row.get("node_type") or "Unknown"),
            "canonical_key": str(row.get("canonical_key") or row.get("node_id") or "node"),
            "display_name": str(row.get("display_name") or "node"),
            "confidence": float(row.get("confidence") or 0.0),
            "attrs": attrs,
            "updated_at": row.get("updated_at"),
        }

    return Module4InsightRuntimeHelpers(
        to_float=lambda value, default=0.0: float(value) if value is not None else float(default),
        to_int=lambda value, default=0: int(value) if value is not None else int(default),
        as_list=_as_list,
        rule_scope=lambda _: "document",
        evaluate_rule_hit=lambda _rule, _context: None,
        normalize_graph_node_row=_normalize_graph_node_row,
        load_evidence_for_node=load_evidence_for_node,
        load_artifact_neighborhood=load_artifact_neighborhood,
        supported_rule_kinds={"deterministic"},
    )


def test_explain_node_uses_artifact_neighborhood_path() -> None:
    called = {"artifact_neighborhood": False}

    async def _load_artifact_neighborhood(
        tenant_id: str,
        node_id: str,
        depth: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        called["artifact_neighborhood"] = True
        assert tenant_id == "tenant-a"
        assert node_id == "ns::entity::1"
        assert depth == 1
        assert limit == 40
        return (
            [
                {
                    "node_id": "ns::entity::1",
                    "node_type": "Entity",
                    "display_name": "Acme",
                    "canonical_key": "entity::acme",
                    "attrs": {"graphrag_id": "ent-1"},
                },
                {
                    "node_id": "ns::entity::2",
                    "node_type": "Entity",
                    "display_name": "Contoso",
                    "canonical_key": "entity::contoso",
                    "attrs": {"graphrag_id": "ent-2"},
                },
            ],
            [
                {
                    "edge_id": "edge::related_to::1",
                    "source_node_id": "ns::entity::1",
                    "target_node_id": "ns::entity::2",
                    "relation_type": "related_to",
                }
            ],
        )

    async def _load_evidence_for_node(
        tenant_id: str,
        node_row: Dict[str, Any],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        assert tenant_id == "tenant-a"
        assert str(node_row.get("node_id") or "") == "ns::entity::1"
        assert limit == 10
        return [{"evidence_id": "ev-1", "snippet": "Acme signed with Contoso."}]

    helpers = _build_helpers(
        load_artifact_neighborhood=_load_artifact_neighborhood,
        load_evidence_for_node=_load_evidence_for_node,
    )
    result = asyncio.run(
        explain_response(
            storage=_NoopStorage(),
            helpers=helpers,
            tenant_id="tenant-a",
            body=ExplainRequest(node_id="ns::entity::1"),
        )
    )

    assert called["artifact_neighborhood"] is True
    assert "Acme" in result.conclusion
    assert len(result.reasoning_steps) >= 1
    assert len(result.evidence) == 1


def test_explain_node_returns_404_when_artifact_neighborhood_missing() -> None:
    async def _load_artifact_neighborhood(
        tenant_id: str,
        node_id: str,
        depth: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        return [], []

    async def _load_evidence_for_node(
        tenant_id: str,
        node_row: Dict[str, Any],
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return []

    helpers = _build_helpers(
        load_artifact_neighborhood=_load_artifact_neighborhood,
        load_evidence_for_node=_load_evidence_for_node,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            explain_response(
                storage=_NoopStorage(),
                helpers=helpers,
                tenant_id="tenant-a",
                body=ExplainRequest(node_id="ns::missing"),
            )
        )

    assert exc.value.status_code == 404
