from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            text = _normalize_text(item)
            if text and text not in out:
                out.append(text)
        return out

    text = _normalize_text(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            out: List[str] = []
            for item in parsed:
                normalized = _normalize_text(item)
                if normalized and normalized not in out:
                    out.append(normalized)
            return out
    normalized = text.replace(";", ",").replace("|", ",")
    out: List[str] = []
    for item in normalized.split(","):
        item_text = _normalize_text(item)
        if item_text and item_text not in out:
            out.append(item_text)
    return out


def _read_rows(path: Path, *, required: bool = False) -> List[Dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except Exception:
        return []

    if not path.exists():
        if required:
            raise FileNotFoundError(str(path))
        return []
    return list(pq.read_table(path).to_pylist())


def _first_existing_path(root: Path, candidates: Sequence[str]) -> Optional[Path]:
    for name in candidates:
        path = root / name
        if path.exists():
            return path
    return None


def _read_rows_any(artifacts_dir: Path, *, candidates: Sequence[str], required: bool) -> List[Dict[str, Any]]:
    path = _first_existing_path(artifacts_dir, candidates)
    if path is None:
        if required:
            raise FileNotFoundError(",".join(candidates))
        return []
    return _read_rows(path, required=required)


def _first_non_empty_text(row: Dict[str, Any], keys: Sequence[str], default: str = "") -> str:
    for key in keys:
        value = _normalize_text(row.get(key))
        if value:
            return value
    return default


def _row_list(row: Dict[str, Any], keys: Sequence[str]) -> List[str]:
    out: List[str] = []
    for key in keys:
        if key not in row or row.get(key) is None:
            continue
        for value in _to_list(row.get(key)):
            normalized = _normalize_text(value)
            if normalized and normalized not in out:
                out.append(normalized)
        if out:
            break
    return out


def _document_ids(row: Dict[str, Any]) -> List[str]:
    values = _row_list(row, ("document_ids",))
    if values:
        return values
    single = _normalize_text(row.get("document_id"))
    return [single] if single else []


def _text_unit_ids(row: Dict[str, Any]) -> List[str]:
    return _row_list(row, ("text_unit_ids",))


def _community_id(row: Dict[str, Any]) -> str:
    return _first_non_empty_text(row, ("community", "community_id", "id"))


def _excerpt(text: str, *, max_chars: int = 72) -> str:
    value = _normalize_text(text)
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3].rstrip()}..."


_ZH_COMMA = "\u3001"
_ZH_COMMUNITY_SUFFIX = "\u793e\u533a"
_ZH_REPORT_SUFFIX = "\u62a5\u544a"
_GENERIC_COMMUNITY_RE = re.compile(r"^\s*community[\s_\-]*\d+\s*$", re.IGNORECASE)
_GENERIC_REPORT_RE = re.compile(r"^\s*report[\s_\-]*[a-z0-9\-]+\s*$", re.IGNORECASE)
_HEXISH_RE = re.compile(r"^[0-9a-f][0-9a-f\-]{11,}$", re.IGNORECASE)
_PLACEHOLDER_ENTITY_RE = re.compile(r"^\s*(entity|node|community)[\s_\-#]*\d*\s*$", re.IGNORECASE)
_ARTIFACT_ENTITY_PREFIX_RE = re.compile(
    r"^(?:photo:|table[_\-]|figure[_\-]|image[_\-]|chart[_\-]|sheet[_\-]|workbook[_\-])",
    re.IGNORECASE,
)
_METRIC_ONLY_RE = re.compile(
    r"^(?:比上年)?(?:增长|下降|提高|增加|减少|增产|减产|上涨|回落)?\s*\d+(?:\.\d+)?\s*(?:%|‰)?$",
    re.IGNORECASE,
)
_NOISY_ENTITY_TERMS = (
    "assistant",
    "gemini",
    "payload",
    "markdown",
    "worksheet",
    "spreadsheet",
    "table schema",
    "chart schema",
    "table summary",
    "chart summary",
)
_ZH_UNNAMED_COMMUNITY = "\u672a\u547d\u540d\u793e\u533a"
_METRIC_HEADER_KEYWORDS = (
    "RATE",
    "GROWTH",
    "BALANCE",
    "TOTAL",
    "RATIO",
    "COUNT",
    "SHARE",
    "INCOME",
    "EXPENDITURE",
    "REVENUE",
    "OUTPUT",
    "USERS",
    "YEAR",
    "ANNUAL",
    "PERCENT",
    "INDICATOR",
    "INDEX",
)


def _contains_cjk(value: str) -> bool:
    for char in str(value or ""):
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF:
            return True
    return False


def _is_placeholder_community_title(title: str, community_id: str) -> bool:
    normalized = _normalize_text(title)
    if not normalized:
        return True
    lower_title = normalized.lower()
    lower_id = _normalize_text(community_id).lower()
    community_token = lower_id.split("::")[-1] if lower_id else ""
    if _GENERIC_COMMUNITY_RE.match(normalized):
        return True
    if lower_title in {"community", "community report", "report"}:
        return True
    if _HEXISH_RE.match(lower_title):
        return True
    if lower_title in {lower_id, community_token} and community_token and (
        _HEXISH_RE.match(community_token) or community_token.isdigit()
    ):
        return True
    return False


def _is_generic_report_title(title: str, report_id: str) -> bool:
    normalized = _normalize_text(title)
    if not normalized:
        return True
    lower_title = normalized.lower()
    lower_id = _normalize_text(report_id).lower()
    if _GENERIC_REPORT_RE.match(normalized):
        return True
    if lower_title == lower_id and (_HEXISH_RE.match(lower_id) or lower_id.isdigit()):
        return True
    return False


def _is_cjk_entity_graph(nodes: Sequence[Dict[str, Any]]) -> bool:
    entity_names: List[str] = []
    for node in nodes:
        if str(node.get("node_type") or "").strip().lower() != "entity":
            continue
        display_name = _normalize_text(node.get("display_name"))
        if display_name:
            entity_names.append(display_name)
    if not entity_names:
        return False
    cjk_hits = sum(1 for name in entity_names if _contains_cjk(name))
    return cjk_hits >= 1


def _prefer_cjk_entity_rows(rows: Sequence[Dict[str, Any]]) -> bool:
    names: List[str] = []
    for row in rows:
        name = _first_non_empty_text(row, ("name", "title", "id"))
        if name:
            names.append(name)
    if not names:
        return False
    cjk_hits = sum(1 for name in names if _contains_cjk(name))
    return cjk_hits >= 1


def _looks_like_metric_header(label: str, *, prefer_cjk: bool) -> bool:
    if _contains_cjk(label):
        return False
    normalized = _normalize_text(label).replace("-", " ").replace("_", " ")
    if len(normalized) < 18:
        return False
    tokens = [item for item in normalized.split() if item]
    if len(tokens) < 3:
        return False
    letters = [char for char in normalized if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / float(len(letters))
    if upper_ratio < 0.9:
        return False
    upper_text = normalized.upper()
    has_metric_keyword = any(keyword in upper_text for keyword in _METRIC_HEADER_KEYWORDS)
    if has_metric_keyword:
        return True
    return prefer_cjk and len(tokens) >= 4 and len(normalized) >= 28


def _looks_metric_only_label(label: str) -> bool:
    normalized = _normalize_text(label)
    if not normalized:
        return False
    return bool(_METRIC_ONLY_RE.fullmatch(normalized))


def _is_noisy_entity_label_legacy(label: str, *, prefer_cjk: bool) -> bool:
    normalized = _normalize_text(label)
    if not normalized:
        return True
    if len(normalized) <= 1:
        return True
    if _PLACEHOLDER_ENTITY_RE.match(normalized):
        return True
    if _HEXISH_RE.match(normalized):
        return True
    if re.fullmatch(r"\d+(?:[\-_/.:]\d+)*", normalized):
        return True
    if _looks_metric_only_label(normalized):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return True
    if re.search(r"```|<table|</table>|\|\s*:?-+:?\s*\|", normalized, re.IGNORECASE):
        return True
    if _ARTIFACT_ENTITY_PREFIX_RE.match(normalized):
        return True
    lowered = normalized.lower()
    if any(term in lowered for term in _NOISY_ENTITY_TERMS):
        return True
    if lowered.startswith("timestamp ") or lowered.startswith("model connectivity check"):
        return True
    if "docx内嵌图像" in lowered or "docx_media" in lowered or lowered.startswith("photo:"):
        return True
    if ("|" in normalized or "｜" in normalized) and sum(char.isdigit() for char in normalized) >= 2:
        return True
    letter_or_cjk = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", normalized))
    symbol_count = len(re.findall(r"[^\w\u4e00-\u9fff\s]", normalized))
    if letter_or_cjk == 0:
        return True
    if symbol_count / max(1, len(normalized)) >= 0.46:
        return True
    if len(normalized) >= 64 and re.search(r"[。！？；]", normalized):
        return True
    if len(normalized) >= 20 and re.search(r"[，。！？；：/（）]", normalized):
        return True
    if _looks_like_metric_header(normalized, prefer_cjk=prefer_cjk):
        return True
    return False


def _compact_entity_label_legacy(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"\.(?:docx|doc|pdf|xlsx|xls|md|txt)$", "", text, flags=re.IGNORECASE).strip()
    if len(text) <= 18:
        return text
    parts = [part.strip() for part in re.split(r"[，,;；、|/（）()\\\-:：]", text) if part.strip()]
    for part in parts:
        if _contains_cjk(part) and 2 <= len(part) <= 18:
            return part
    return text[:18].rstrip()


def _is_noisy_entity_label(label: str, *, prefer_cjk: bool) -> bool:
    normalized = _normalize_text(label)
    if not normalized:
        return True
    if len(normalized) <= 1:
        return True
    if _PLACEHOLDER_ENTITY_RE.match(normalized):
        return True
    if _HEXISH_RE.match(normalized):
        return True
    if re.fullmatch(r"\d+(?:[\-_/.:]\d+)*", normalized):
        return True
    if _looks_metric_only_label(normalized):
        return True
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return True
    if re.search(r"```|<table|</table>|\|\s*:?-+:?\s*\|", normalized, re.IGNORECASE):
        return True
    if _ARTIFACT_ENTITY_PREFIX_RE.match(normalized):
        return True
    lowered = normalized.lower()
    if any(term in lowered for term in _NOISY_ENTITY_TERMS):
        return True
    if lowered.startswith("timestamp ") or lowered.startswith("model connectivity check"):
        return True
    if "docx\u5185\u5d4c\u56fe\u50cf" in lowered or "docx_media" in lowered or lowered.startswith("photo:"):
        return True
    if ("|" in normalized or "\uFF5C" in normalized) and sum(char.isdigit() for char in normalized) >= 2:
        return True
    letter_or_cjk = len(re.findall(r"[A-Za-z\u4e00-\u9fff]", normalized))
    symbol_count = len(re.findall(r"[^\w\u4e00-\u9fff\s]", normalized))
    if letter_or_cjk == 0:
        return True
    if symbol_count / max(1, len(normalized)) >= 0.46:
        return True
    if len(normalized) >= 64 and re.search(r"[\u3002\uFF01\uFF1F\uFF1B]", normalized):
        return True
    if len(normalized) >= 20 and re.search(r"[\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A/\uFF08\uFF09]", normalized):
        return True
    if _looks_like_metric_header(normalized, prefer_cjk=prefer_cjk):
        return True
    return False


def _compact_entity_label(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    text = re.sub(r"\.(?:docx|doc|pdf|xlsx|xls|md|txt)$", "", text, flags=re.IGNORECASE).strip()
    if len(text) <= 18:
        return text
    parts = [part.strip() for part in re.split(r"[,\uFF0C;\uFF1B/\u3001\(\)\uFF08\uFF09\\\-:]+", text) if part.strip()]
    for part in parts:
        if _contains_cjk(part) and 2 <= len(part) <= 18:
            return part
    return text[:18].rstrip()


def _build_community_title_from_entities(entity_names: Sequence[str]) -> str:
    seen: set[str] = set()
    cjk_names: List[str] = []
    fallback_names: List[str] = []
    for value in entity_names:
        text = _compact_entity_label(value)
        if not text:
            continue
        lower_text = text.lower()
        if lower_text in seen:
            continue
        seen.add(lower_text)
        if _GENERIC_COMMUNITY_RE.match(text) or _GENERIC_REPORT_RE.match(text):
            continue
        if _HEXISH_RE.match(text):
            continue
        if _is_noisy_entity_label(text, prefer_cjk=True):
            continue
        if _contains_cjk(text):
            cjk_names.append(text)
        else:
            fallback_names.append(text)

    selected = cjk_names[:3] if cjk_names else fallback_names[:2]
    if not selected:
        return ""
    merged = _ZH_COMMA.join(selected)
    if len(merged) > 26:
        merged = merged[:23].rstrip() + "..."
    return f"{merged}{_ZH_COMMUNITY_SUFFIX}"


def _backfill_cjk_community_titles(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
    if not nodes or not edges:
        return

    node_map = {str(item.get("node_id") or ""): item for item in nodes}
    community_entity_names: Dict[str, List[str]] = {}
    community_report_node_ids: Dict[str, List[str]] = {}

    def _push_unique(map_obj: Dict[str, List[str]], key: str, value: str) -> None:
        if not key or not value:
            return
        values = map_obj.get(key)
        if values is None:
            values = []
            map_obj[key] = values
        if value not in values:
            values.append(value)

    for edge in edges:
        source_id = str(edge.get("source_node_id") or "")
        target_id = str(edge.get("target_node_id") or "")
        relation_type = str(edge.get("relation_type") or "").strip().lower()
        source = node_map.get(source_id)
        target = node_map.get(target_id)
        if not source or not target:
            continue
        source_type = str(source.get("node_type") or "").strip().lower()
        target_type = str(target.get("node_type") or "").strip().lower()

        if relation_type == "in_community":
            if source_type == "entity" and target_type == "community":
                _push_unique(community_entity_names, target_id, _normalize_text(source.get("display_name")))
            elif target_type == "entity" and source_type == "community":
                _push_unique(community_entity_names, source_id, _normalize_text(target.get("display_name")))
        elif relation_type == "has_report":
            if source_type == "community":
                _push_unique(community_report_node_ids, source_id, target_id)
            elif target_type == "community":
                _push_unique(community_report_node_ids, target_id, source_id)

    for node_id, node in node_map.items():
        if str(node.get("node_type") or "").strip().lower() != "community":
            continue
        current_title = _normalize_text(node.get("display_name"))
        entity_names = community_entity_names.get(node_id, [])
        generated_title = _build_community_title_from_entities(entity_names)
        if generated_title and (_is_placeholder_community_title(current_title, node_id) or not _contains_cjk(current_title)):
            node["display_name"] = generated_title
            current_title = generated_title
        elif _is_placeholder_community_title(current_title, node_id):
            attrs = dict(node.get("attrs") or {})
            community_hint = _normalize_text(attrs.get("graphrag_id")) or _normalize_text(node_id.split("::")[-1])
            if _HEXISH_RE.match(community_hint) or community_hint.isdigit():
                fallback_title = generated_title or _ZH_UNNAMED_COMMUNITY
            else:
                fallback_title = f"{_ZH_COMMUNITY_SUFFIX} {community_hint}" if community_hint else _ZH_COMMUNITY_SUFFIX
            node["display_name"] = fallback_title
            current_title = fallback_title

        attrs = dict(node.get("attrs") or {})
        if current_title:
            attrs["community_title"] = current_title
            node["attrs"] = attrs

        for report_node_id in community_report_node_ids.get(node_id, []):
            report_node = node_map.get(report_node_id)
            if not report_node:
                continue
            report_type = str(report_node.get("node_type") or "").strip().lower()
            if report_type != "communityreport":
                continue
            report_title = _normalize_text(report_node.get("display_name"))
            should_backfill = _is_generic_report_title(report_title, report_node_id) or (
                current_title and not _contains_cjk(report_title)
            )
            if should_backfill and current_title:
                final_report_title = (
                    current_title if current_title.endswith(_ZH_REPORT_SUFFIX) else f"{current_title}{_ZH_REPORT_SUFFIX}"
                )
                report_node["display_name"] = final_report_title
            report_attrs = dict(report_node.get("attrs") or {})
            if current_title:
                report_attrs["community_title"] = current_title
            report_node["attrs"] = report_attrs


def resolve_artifacts_dir_from_graph_file(graph_file: Dict[str, Any]) -> Optional[Path]:
    metadata = graph_file.get("metadata") if isinstance(graph_file.get("metadata"), dict) else {}
    candidates: List[str] = []
    for key in ("artifacts_dir",):
        value = _normalize_text(metadata.get(key))
        if value:
            candidates.append(value)

    output_dir = _normalize_text(metadata.get("output_dir"))
    if output_dir:
        candidates.append(str(Path(output_dir) / "artifacts"))

    for item in candidates:
        path = Path(item).resolve()
        if path.exists() and path.is_dir():
            return path
    return None


@dataclass(frozen=True)
class GraphRAGArtifactGraph:
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    workspace_id: Optional[str]
    source: str = "graphrag:artifacts:file"

    @property
    def node_map(self) -> Dict[str, Dict[str, Any]]:
        return {str(item.get("node_id") or ""): item for item in self.nodes}


def load_artifact_graph_snapshot(graph_file: Dict[str, Any]) -> Optional[GraphRAGArtifactGraph]:
    artifacts_dir = resolve_artifacts_dir_from_graph_file(graph_file)
    if artifacts_dir is None:
        return None

    try:
        documents = _read_rows_any(
            artifacts_dir,
            candidates=("create_final_documents.parquet", "documents.parquet"),
            required=True,
        )
        text_units = _read_rows_any(
            artifacts_dir,
            candidates=("create_final_text_units.parquet", "text_units.parquet"),
            required=True,
        )
        entities = _read_rows_any(
            artifacts_dir,
            candidates=("create_final_entities.parquet", "entities.parquet"),
            required=True,
        )
        relationships = _read_rows_any(
            artifacts_dir,
            candidates=("create_final_relationships.parquet", "relationships.parquet"),
            required=True,
        )
    except Exception:
        return None

    communities = _read_rows_any(
        artifacts_dir,
        candidates=("create_final_communities.parquet", "communities.parquet"),
        required=False,
    )
    community_reports = _read_rows_any(
        artifacts_dir,
        candidates=("create_final_community_reports.parquet", "community_reports.parquet"),
        required=False,
    )
    covariates = _read_rows_any(
        artifacts_dir,
        candidates=("create_final_covariates.parquet", "covariates.parquet"),
        required=False,
    )
    prefer_cjk_entities = _prefer_cjk_entity_rows(entities)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[Tuple[str, str, str]] = set()
    workspace_id = _normalize_text(graph_file.get("workspace_id")) or None
    file_hash = _normalize_text(graph_file.get("file_hash"))

    doc_nodes: Dict[str, str] = {}
    chunk_nodes: Dict[str, str] = {}
    entity_nodes: Dict[str, str] = {}
    entity_name_to_id: Dict[str, str] = {}
    community_nodes: Dict[str, str] = {}
    report_nodes: Dict[str, str] = {}

    def _push_node(
        *,
        node_id: str,
        node_type: str,
        canonical_key: str,
        display_name: str,
        attrs: Dict[str, Any],
        confidence: float = 1.0,
    ) -> None:
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "canonical_key": canonical_key,
                "display_name": display_name or canonical_key or node_id,
                "confidence": confidence,
                "attrs": attrs,
                "updated_at": None,
            }
        )

    def _push_edge(
        *,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        confidence: float = 1.0,
        risk_score: float = 0.0,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not source_node_id or not target_node_id or source_node_id == target_node_id:
            return
        key = (source_node_id, target_node_id, relation_type)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge_id = f"edge::{relation_type}::{source_node_id}::{target_node_id}"
        edges.append(
            {
                "edge_id": edge_id,
                "source_node_id": source_node_id,
                "target_node_id": target_node_id,
                "relation_type": relation_type,
                "direction": "out",
                "confidence": confidence,
                "risk_score": risk_score,
                "attrs": attrs or {},
                "updated_at": None,
            }
        )

    for row in documents:
        graphrag_id = _normalize_text(row.get("id"))
        if not graphrag_id:
            continue
        node_id = f"doc::{graphrag_id}"
        doc_nodes[graphrag_id] = node_id
        _push_node(
            node_id=node_id,
            node_type="Document",
            canonical_key=f"document::{graphrag_id}",
            display_name=_normalize_text(row.get("title")) or graphrag_id,
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "file_hash": file_hash,
                "graphrag_id": graphrag_id,
                "human_readable_id": _normalize_text(row.get("human_readable_id")),
                "raw_content": _first_non_empty_text(row, ("raw_content", "text", "raw_data")),
            },
        )

    for row in text_units:
        graphrag_id = _normalize_text(row.get("id"))
        if not graphrag_id:
            continue
        text = _normalize_text(row.get("text"))
        document_ids = _document_ids(row)
        entity_ids = _row_list(row, ("entity_ids",))
        relationship_ids = _row_list(row, ("relationship_ids",))
        node_id = f"chunk::{graphrag_id}"
        chunk_nodes[graphrag_id] = node_id
        _push_node(
            node_id=node_id,
            node_type="Chunk",
            canonical_key=f"chunk::{graphrag_id}",
            display_name=_excerpt(text) or graphrag_id,
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "graphrag_id": graphrag_id,
                "text": text,
                "n_tokens": row.get("n_tokens"),
                "document_ids": document_ids,
                "entity_ids": entity_ids,
                "relationship_ids": relationship_ids,
                "human_readable_id": _normalize_text(row.get("human_readable_id")),
            },
        )
        for document_id in document_ids:
            document_node_id = doc_nodes.get(document_id)
            if document_node_id:
                _push_edge(
                    source_node_id=document_node_id,
                    target_node_id=node_id,
                    relation_type="has_chunk",
                    attrs={
                        "graph_source": "graphrag_artifacts",
                        "workspace_id": workspace_id,
                        "chunk_id": graphrag_id,
                        "document_id": document_id,
                    },
                )

    for row in entities:
        graphrag_id = _normalize_text(row.get("id"))
        if not graphrag_id:
            continue
        name = _first_non_empty_text(row, ("name", "title"), graphrag_id)
        if _is_noisy_entity_label(name, prefer_cjk=prefer_cjk_entities):
            continue
        entity_type = _normalize_text(row.get("type")) or "entity"
        text_unit_ids = _text_unit_ids(row)
        community_ids = _row_list(row, ("community_ids",))
        node_id = f"entity::{graphrag_id}"
        entity_nodes[graphrag_id] = node_id
        entity_name_to_id[name.lower()] = node_id
        _push_node(
            node_id=node_id,
            node_type="Entity",
            canonical_key=f"entity::{graphrag_id}",
            display_name=name,
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "graphrag_id": graphrag_id,
                "entity_type": entity_type,
                "description": _normalize_text(row.get("description")),
                "text_unit_ids": text_unit_ids,
                "community_ids": community_ids,
            },
        )
        for text_unit_id in text_unit_ids:
            chunk_node_id = chunk_nodes.get(text_unit_id)
            if chunk_node_id:
                _push_edge(
                    source_node_id=chunk_node_id,
                    target_node_id=node_id,
                    relation_type="has_entity",
                    attrs={
                        "graph_source": "graphrag_artifacts",
                        "workspace_id": workspace_id,
                        "text_unit_id": text_unit_id,
                        "entity_id": graphrag_id,
                    },
                )

    relationship_refs: Dict[str, Tuple[str, str]] = {}
    for row in relationships:
        rel_id = _normalize_text(row.get("id"))
        source_name = _normalize_text(row.get("source"))
        target_name = _normalize_text(row.get("target"))
        source_node_id = entity_name_to_id.get(source_name.lower())
        target_node_id = entity_name_to_id.get(target_name.lower())
        if not source_node_id or not target_node_id:
            continue
        if rel_id:
            relationship_refs[rel_id] = (source_node_id, target_node_id)
        _push_edge(
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type="related_to",
            confidence=max(0.0, min(1.0, _to_float(row.get("weight"), 0.0))),
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "graphrag_id": rel_id,
                "description": _normalize_text(row.get("description")),
                "weight": _to_float(row.get("weight"), 0.0),
                "rank": row.get("rank") if row.get("rank") is not None else row.get("combined_degree"),
                "combined_degree": row.get("combined_degree"),
                "text_unit_ids": _text_unit_ids(row),
            },
        )

    for row in communities:
        community_id = _community_id(row)
        if not community_id:
            continue
        node_id = community_nodes.get(community_id) or f"community::{community_id}"
        community_nodes[community_id] = node_id
        text_unit_ids = _text_unit_ids(row)
        relationship_ids = _row_list(row, ("relationship_ids",))
        _push_node(
            node_id=node_id,
            node_type="Community",
            canonical_key=f"community::{community_id}",
            display_name=_normalize_text(row.get("title")) or community_id,
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "graphrag_id": community_id,
                "level": row.get("level"),
                "text_unit_ids": text_unit_ids,
                "relationship_ids": relationship_ids,
            },
        )

    for row in community_reports:
        report_id = _first_non_empty_text(row, ("id", "report_id", "human_readable_id"))
        community_id = _community_id(row)
        if not report_id and not community_id:
            continue
        if not community_id:
            community_id = report_id
        community_node_id = community_nodes.get(community_id)
        if not community_node_id:
            community_node_id = f"community::{community_id}"
            community_nodes[community_id] = community_node_id
            _push_node(
                node_id=community_node_id,
                node_type="Community",
                canonical_key=f"community::{community_id}",
                display_name=community_id,
                attrs={
                    "graph_source": "graphrag_artifacts",
                    "workspace_id": workspace_id,
                    "graphrag_id": community_id,
                },
            )

        report_node_id = f"community_report::{report_id or community_id}"
        report_nodes[report_id or community_id] = report_node_id
        _push_node(
            node_id=report_node_id,
            node_type="CommunityReport",
            canonical_key=f"community_report::{report_id or community_id}",
            display_name=_normalize_text(row.get("title")) or f"Report {report_id or community_id}",
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "report_id": report_id or community_id,
                "graphrag_id": community_id,
                "summary": _normalize_text(row.get("summary")),
                "full_content": _normalize_text(row.get("full_content")),
                "rank": row.get("rank"),
                "rank_explanation": _first_non_empty_text(row, ("rank_explanation", "rating_explanation")),
                "findings": row.get("findings"),
            },
        )
        _push_edge(
            source_node_id=community_node_id,
            target_node_id=report_node_id,
            relation_type="has_report",
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "community_id": community_id,
                "report_id": report_id,
            },
        )

    for row in entities:
        entity_id = _normalize_text(row.get("id"))
        if not entity_id:
            continue
        entity_node_id = entity_nodes.get(entity_id)
        if not entity_node_id:
            continue
        for community_id in _to_list(row.get("community_ids")):
            community_node_id = community_nodes.get(community_id)
            if community_node_id:
                _push_edge(
                    source_node_id=entity_node_id,
                    target_node_id=community_node_id,
                    relation_type="in_community",
                    attrs={
                        "graph_source": "graphrag_artifacts",
                        "workspace_id": workspace_id,
                        "community_id": community_id,
                    },
                )

    for row in communities:
        community_id = _community_id(row)
        community_node_id = community_nodes.get(community_id)
        if not community_id or not community_node_id:
            continue
        for rel_id in _row_list(row, ("relationship_ids",)):
            ref = relationship_refs.get(rel_id)
            if not ref:
                continue
            for entity_node_id in ref:
                _push_edge(
                    source_node_id=entity_node_id,
                    target_node_id=community_node_id,
                    relation_type="in_community",
                    attrs={
                        "graph_source": "graphrag_artifacts",
                        "workspace_id": workspace_id,
                        "community_id": community_id,
                        "relationship_id": rel_id,
                    },
                )

    for row in covariates:
        covariate_id = _normalize_text(row.get("id"))
        text_unit_id = _normalize_text(row.get("text_unit_id"))
        if not covariate_id:
            continue
        covariate_node_id = f"covariate::{covariate_id}"
        _push_node(
            node_id=covariate_node_id,
            node_type="Covariate",
            canonical_key=f"covariate::{covariate_id}",
            display_name=_first_non_empty_text(row, ("title", "description"), covariate_id),
            attrs={
                "graph_source": "graphrag_artifacts",
                "workspace_id": workspace_id,
                "graphrag_id": covariate_id,
                "text_unit_id": text_unit_id,
            },
        )
        if text_unit_id and text_unit_id in chunk_nodes:
            _push_edge(
                source_node_id=chunk_nodes[text_unit_id],
                target_node_id=covariate_node_id,
                relation_type="has_covariate",
                attrs={
                    "graph_source": "graphrag_artifacts",
                    "workspace_id": workspace_id,
                    "text_unit_id": text_unit_id,
                    "covariate_id": covariate_id,
                },
            )

    _backfill_cjk_community_titles(nodes=nodes, edges=edges)

    if not nodes:
        return None
    return GraphRAGArtifactGraph(nodes=nodes, edges=edges, workspace_id=workspace_id)


def filter_artifact_graph(
    *,
    graph: GraphRAGArtifactGraph,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    def _type_key(value: Any) -> str:
        return str(value or "").strip().lower()

    def _node_type_priority(value: Any) -> int:
        key = _type_key(value)
        if key == "community":
            return 0
        if key in {"communityreport", "community_report", "report"}:
            return 1
        if key == "entity":
            return 2
        if key == "document":
            return 3
        if key in {"textunit", "text_unit", "chunk"}:
            return 4
        if key == "covariate":
            return 5
        return 9

    def _edge_type_priority(value: Any) -> int:
        key = _type_key(value)
        if key == "in_community":
            return 0
        if key == "related_to":
            return 1
        if key == "has_report":
            return 2
        if key == "has_entity":
            return 3
        if key == "has_chunk":
            return 4
        return 9

    def _node_importance(node: Dict[str, Any], degree_by_node: Dict[str, int]) -> float:
        attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
        node_id = str(node.get("node_id") or "")
        return max(
            _to_float(attrs.get("importance"), 0.0),
            _to_float(attrs.get("weight"), 0.0),
            _to_float(attrs.get("rank"), 0.0),
            _to_float(attrs.get("combined_degree"), 0.0),
            _to_float(node.get("confidence"), 0.0),
            float(degree_by_node.get(node_id, 0)),
        )

    node_types_set = {_type_key(value) for value in node_types if _type_key(value)}
    relation_types_set = {_type_key(value) for value in relation_types if _type_key(value)}
    limit_nodes_value = max(1, int(limit_nodes))
    limit_edges_value = max(1, int(limit_edges))

    nodes = list(graph.nodes)
    if node_types_set:
        nodes = [item for item in nodes if _type_key(item.get("node_type")) in node_types_set]
    if not nodes:
        return [], []

    candidate_node_ids = {str(item.get("node_id") or "") for item in nodes if str(item.get("node_id") or "")}
    edges = [
        item
        for item in graph.edges
        if str(item.get("source_node_id") or "") in candidate_node_ids
        and str(item.get("target_node_id") or "") in candidate_node_ids
    ]
    if relation_types_set:
        edges = [item for item in edges if _type_key(item.get("relation_type")) in relation_types_set]

    degree_by_node: Dict[str, int] = {}
    for edge in edges:
        src = str(edge.get("source_node_id") or "")
        tgt = str(edge.get("target_node_id") or "")
        if src:
            degree_by_node[src] = degree_by_node.get(src, 0) + 1
        if tgt:
            degree_by_node[tgt] = degree_by_node.get(tgt, 0) + 1

    ranked_nodes = sorted(
        [dict(item) for item in nodes],
        key=lambda row: (
            _node_type_priority(row.get("node_type")),
            -_node_importance(row, degree_by_node),
            -degree_by_node.get(str(row.get("node_id") or ""), 0),
            str(row.get("display_name") or ""),
            str(row.get("node_id") or ""),
        ),
    )
    selected_nodes = ranked_nodes[:limit_nodes_value]
    selected_node_ids = {str(item.get("node_id") or "") for item in selected_nodes}

    selected_edges = [
        dict(item)
        for item in edges
        if str(item.get("source_node_id") or "") in selected_node_ids
        and str(item.get("target_node_id") or "") in selected_node_ids
    ]
    selected_edges = sorted(
        selected_edges,
        key=lambda row: (
            _edge_type_priority(row.get("relation_type")),
            -max(
                _to_float((row.get("attrs") or {}).get("weight") if isinstance(row.get("attrs"), dict) else 0.0, 0.0),
                _to_float(row.get("confidence"), 0.0),
            ),
            str(row.get("source_node_id") or ""),
            str(row.get("target_node_id") or ""),
            str(row.get("edge_id") or ""),
        ),
    )[:limit_edges_value]
    return selected_nodes, selected_edges


def artifact_neighborhood(
    *,
    graph: GraphRAGArtifactGraph,
    node_id: str,
    depth: int,
    relation_types: Sequence[str],
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    relation_types_set = {str(value).strip() for value in relation_types if str(value).strip()}
    depth_value = max(1, min(4, int(depth)))
    limit_value = max(20, min(5000, int(limit)))
    node_key = str(node_id or "").strip()
    node_map = graph.node_map
    if node_key not in node_map:
        return [], []

    edges = list(graph.edges)
    if relation_types_set:
        edges = [item for item in edges if str(item.get("relation_type") or "") in relation_types_set]

    visited = {node_key}
    frontier = {node_key}
    selected_edges: Dict[str, Dict[str, Any]] = {}
    for _ in range(depth_value):
        if not frontier or len(visited) >= limit_value:
            break
        next_frontier: set[str] = set()
        for edge in edges:
            src = str(edge.get("source_node_id") or "")
            tgt = str(edge.get("target_node_id") or "")
            if src not in frontier and tgt not in frontier:
                continue
            selected_edges[str(edge.get("edge_id") or f"{src}->{tgt}")] = edge
            for candidate in (src, tgt):
                if candidate and candidate not in visited and len(visited) < limit_value:
                    visited.add(candidate)
                    next_frontier.add(candidate)
        frontier = next_frontier

    selected_nodes = [dict(node_map[item]) for item in visited if item in node_map]
    selected_edge_rows = list(selected_edges.values())
    return selected_nodes[:limit_value], selected_edge_rows[: limit_value * 2]
