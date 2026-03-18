from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    username: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls) -> "Neo4jSettings":
        return cls(
            uri=str(os.getenv("MODULE4_NEO4J_URI", os.getenv("NEO4J_URI", "")) or "").strip(),
            username=str(os.getenv("MODULE4_NEO4J_USERNAME", os.getenv("NEO4J_USERNAME", "")) or "").strip(),
            password=str(os.getenv("MODULE4_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "")) or "").strip(),
            database=str(os.getenv("MODULE4_NEO4J_DATABASE", os.getenv("NEO4J_DATABASE", "neo4j")) or "neo4j").strip()
            or "neo4j",
        )

    def is_configured(self) -> bool:
        return bool(self.uri and self.username and self.password)

    def missing_fields(self) -> List[str]:
        missing: List[str] = []
        if not self.uri:
            missing.append("MODULE4_NEO4J_URI")
        if not self.username:
            missing.append("MODULE4_NEO4J_USERNAME")
        if not self.password:
            missing.append("MODULE4_NEO4J_PASSWORD")
        return missing

    def workspace_env(self) -> Dict[str, str]:
        values = {
            "NEO4J_URI": self.uri,
            "NEO4J_USERNAME": self.username,
            "NEO4J_PASSWORD": self.password,
            "NEO4J_DATABASE": self.database,
        }
        return {key: value for key, value in values.items() if value}


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _safe_int(raw: str, default: int) -> int:
    try:
        value = int(str(raw or "").strip())
    except Exception:
        return default
    return max(1, value)


def _safe_float(raw: str, default: float) -> float:
    try:
        value = float(str(raw or "").strip())
    except Exception:
        return default
    return max(0.1, value)


def _as_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


@dataclass(frozen=True)
class Neo4jProjectionResult:
    status: str
    projected_nodes: int = 0
    projected_edges: int = 0
    source_node_count: int = 0
    source_edge_count: int = 0
    skipped_reason: str | None = None
    error_message: str | None = None
    labels: List[str] = field(default_factory=lambda: ["Module4Node"])
    relationship_type: str = "MODULE4_EDGE"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "projected_nodes": self.projected_nodes,
            "projected_edges": self.projected_edges,
            "source_node_count": self.source_node_count,
            "source_edge_count": self.source_edge_count,
            "skipped_reason": self.skipped_reason,
            "error_message": self.error_message,
            "labels": list(self.labels),
            "relationship_type": self.relationship_type,
        }


class Neo4jGraphProjector:
    def __init__(self, settings: Neo4jSettings | None = None) -> None:
        self.settings = settings or Neo4jSettings.from_env()
        self.enabled = _env_flag("MODULE4_NEO4J_PROJECT_ON_READY", True)
        self.max_nodes = _safe_int(os.getenv("MODULE4_NEO4J_PROJECT_MAX_NODES", "5000"), 5000)
        self.max_edges = _safe_int(os.getenv("MODULE4_NEO4J_PROJECT_MAX_EDGES", "10000"), 10000)
        self.timeout_sec = _safe_float(os.getenv("MODULE4_NEO4J_PROJECT_TIMEOUT_SEC", "2.0"), 2.0)

    def refresh_settings(self, settings: Neo4jSettings | None) -> None:
        if settings is not None:
            self.settings = settings

    def project(
        self,
        *,
        tenant_id: str,
        file_hash: str,
        graph_file_id: str | None,
        graph_version_id: str | None,
        workspace_id: str | None,
        nodes: Sequence[Dict[str, Any]],
        edges: Sequence[Dict[str, Any]],
        source_node_count: int | None = None,
        source_edge_count: int | None = None,
    ) -> Neo4jProjectionResult:
        node_total = int(source_node_count if source_node_count is not None else len(nodes))
        edge_total = int(source_edge_count if source_edge_count is not None else len(edges))

        if not self.enabled:
            return Neo4jProjectionResult(
                status="skipped",
                source_node_count=node_total,
                source_edge_count=edge_total,
                skipped_reason="projection_disabled",
            )
        if not self.settings.is_configured():
            return Neo4jProjectionResult(
                status="skipped",
                source_node_count=node_total,
                source_edge_count=edge_total,
                skipped_reason="neo4j_unconfigured",
            )
        if not tenant_id or not file_hash or not graph_version_id:
            return Neo4jProjectionResult(
                status="skipped",
                source_node_count=node_total,
                source_edge_count=edge_total,
                skipped_reason="projection_scope_incomplete",
            )
        if node_total > self.max_nodes or edge_total > self.max_edges:
            return Neo4jProjectionResult(
                status="skipped",
                source_node_count=node_total,
                source_edge_count=edge_total,
                skipped_reason="projection_limits_exceeded",
            )

        try:
            from neo4j import GraphDatabase
        except Exception as exc:
            return Neo4jProjectionResult(
                status="failed",
                source_node_count=node_total,
                source_edge_count=edge_total,
                error_message=f"Neo4j driver import failed: {type(exc).__name__}: {exc}",
            )

        driver = None
        try:
            driver = GraphDatabase.driver(
                self.settings.uri,
                auth=(self.settings.username, self.settings.password),
                max_connection_pool_size=2,
                connection_timeout=self.timeout_sec,
                connection_acquisition_timeout=self.timeout_sec,
                max_transaction_retry_time=0.0,
            )
            with driver.session(database=self.settings.database) as session:
                write_fn = getattr(session, "execute_write", None) or getattr(session, "write_transaction", None)
                if write_fn is None:
                    raise RuntimeError("Neo4j session does not support write transactions")
                write_fn(
                    self._project_tx,
                    tenant_id=tenant_id,
                    file_hash=file_hash,
                    graph_file_id=str(graph_file_id or ""),
                    graph_version_id=str(graph_version_id or ""),
                    workspace_id=str(workspace_id or ""),
                    nodes=self._serialize_nodes(nodes),
                    edges=self._serialize_edges(edges),
                )
            return Neo4jProjectionResult(
                status="success",
                projected_nodes=len(nodes),
                projected_edges=len(edges),
                source_node_count=node_total,
                source_edge_count=edge_total,
            )
        except Exception as exc:
            return Neo4jProjectionResult(
                status="failed",
                projected_nodes=0,
                projected_edges=0,
                source_node_count=node_total,
                source_edge_count=edge_total,
                error_message=f"{type(exc).__name__}: {exc}",
            )
        finally:
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass

    @staticmethod
    def _serialize_nodes(nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for row in nodes:
            attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
            serialized.append(
                {
                    "node_id": str(row.get("node_id") or ""),
                    "node_type": str(row.get("node_type") or "Unknown"),
                    "canonical_key": str(row.get("canonical_key") or ""),
                    "display_name": str(row.get("display_name") or ""),
                    "confidence": float(row.get("confidence") or 0.0),
                    "updated_at": str(row.get("updated_at") or ""),
                    "attrs_json": _as_json_text(attrs),
                }
            )
        return serialized

    @staticmethod
    def _serialize_edges(edges: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for row in edges:
            attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
            serialized.append(
                {
                    "edge_id": str(row.get("edge_id") or ""),
                    "source_node_id": str(row.get("source_node_id") or ""),
                    "target_node_id": str(row.get("target_node_id") or ""),
                    "relation_type": str(row.get("relation_type") or "related_to"),
                    "direction": str(row.get("direction") or "out"),
                    "confidence": float(row.get("confidence") or 0.0),
                    "risk_score": float(row.get("risk_score") or 0.0),
                    "updated_at": str(row.get("updated_at") or ""),
                    "attrs_json": _as_json_text(attrs),
                }
            )
        return serialized

    @staticmethod
    def _project_tx(
        tx: Any,
        *,
        tenant_id: str,
        file_hash: str,
        graph_file_id: str,
        graph_version_id: str,
        workspace_id: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> None:
        tx.run(
            """
            MATCH (n:Module4Node {tenant_id: $tenant_id, file_hash: $file_hash})
            DETACH DELETE n
            """,
            tenant_id=tenant_id,
            file_hash=file_hash,
        ).consume()
        tx.run(
            """
            UNWIND $nodes AS row
            CREATE (n:Module4Node {
              tenant_id: $tenant_id,
              file_hash: $file_hash,
              graph_file_id: $graph_file_id,
              graph_version_id: $graph_version_id,
              workspace_id: $workspace_id,
              node_id: row.node_id
            })
            SET n.node_type = row.node_type,
                n.canonical_key = row.canonical_key,
                n.display_name = row.display_name,
                n.confidence = row.confidence,
                n.updated_at = row.updated_at,
                n.attrs_json = row.attrs_json
            """,
            tenant_id=tenant_id,
            file_hash=file_hash,
            graph_file_id=graph_file_id,
            graph_version_id=graph_version_id,
            workspace_id=workspace_id,
            nodes=nodes,
        ).consume()
        tx.run(
            """
            UNWIND $edges AS row
            MATCH (src:Module4Node {tenant_id: $tenant_id, file_hash: $file_hash, node_id: row.source_node_id})
            MATCH (tgt:Module4Node {tenant_id: $tenant_id, file_hash: $file_hash, node_id: row.target_node_id})
            CREATE (src)-[r:MODULE4_EDGE {
              tenant_id: $tenant_id,
              file_hash: $file_hash,
              graph_file_id: $graph_file_id,
              graph_version_id: $graph_version_id,
              workspace_id: $workspace_id,
              edge_id: row.edge_id
            }]->(tgt)
            SET r.relation_type = row.relation_type,
                r.direction = row.direction,
                r.confidence = row.confidence,
                r.risk_score = row.risk_score,
                r.updated_at = row.updated_at,
                r.attrs_json = row.attrs_json
            """,
            tenant_id=tenant_id,
            file_hash=file_hash,
            graph_file_id=graph_file_id,
            graph_version_id=graph_version_id,
            workspace_id=workspace_id,
            edges=edges,
        ).consume()
