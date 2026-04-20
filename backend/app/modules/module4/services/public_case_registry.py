from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PUBLIC_CASE_FILE_HASH_PREFIX = "public_case::"
PUBLIC_CASE_LIBRARY_TENANT_ID = "public_case_library"


@dataclass(frozen=True)
class Module4PublicCase:
    case_id: str
    source_tenant_id: str
    source_file_hash: str
    display_name: str
    description: Optional[str] = None
    tags: tuple[str, ...] = ()
    sort_order: int = 1000
    enabled: bool = True


@dataclass(frozen=True)
class Module4ResolvedGraphAccess:
    graph_file: Dict[str, Any]
    response_graph_file: Dict[str, Any]
    storage_tenant_id: str
    asset_owner_id: str
    requested_file_hash: str
    storage_file_hash: str
    public_case: Optional[Module4PublicCase] = None


def _module4_root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _registry_path() -> Path:
    configured = str(os.getenv("MODULE4_PUBLIC_CASE_REGISTRY_PATH") or "").strip()
    if not configured:
        return (_module4_root_dir() / "resources" / "public_case_graphs.json").resolve()

    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (_module4_root_dir() / candidate).resolve()


def public_case_file_hash(case_id: str) -> str:
    return f"{PUBLIC_CASE_FILE_HASH_PREFIX}{str(case_id or '').strip()}"


def is_public_case_file_hash(value: Any) -> bool:
    return str(value or "").strip().startswith(PUBLIC_CASE_FILE_HASH_PREFIX)


def _normalize_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items = [str(item).strip() for item in value if str(item).strip()]
    return tuple(items)


def _safe_int(value: Any, default: int = 1000) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_registry_records() -> List[Dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def list_public_cases() -> List[Module4PublicCase]:
    items: List[Module4PublicCase] = []
    for raw in _read_registry_records():
        case_id = str(raw.get("case_id") or "").strip()
        source_tenant_id = str(raw.get("source_tenant_id") or raw.get("tenant_id") or "").strip()
        source_file_hash = str(raw.get("source_file_hash") or raw.get("file_hash") or "").strip()
        display_name = str(raw.get("display_name") or raw.get("title") or "").strip()
        if not case_id or not source_tenant_id or not source_file_hash:
            continue
        items.append(
            Module4PublicCase(
                case_id=case_id,
                source_tenant_id=source_tenant_id,
                source_file_hash=source_file_hash,
                display_name=display_name or case_id,
                description=str(raw.get("description") or "").strip() or None,
                tags=_normalize_tags(raw.get("tags")),
                sort_order=_safe_int(raw.get("sort_order"), 1000),
                enabled=bool(raw.get("enabled", True)),
            )
        )
    return sorted(
        [item for item in items if item.enabled],
        key=lambda item: (item.sort_order, item.display_name.lower(), item.case_id),
    )


def get_public_case(case_reference: str) -> Optional[Module4PublicCase]:
    normalized = str(case_reference or "").strip()
    if not normalized:
        return None
    if normalized.startswith(PUBLIC_CASE_FILE_HASH_PREFIX):
        normalized = normalized[len(PUBLIC_CASE_FILE_HASH_PREFIX) :].strip()
    if not normalized:
        return None

    for item in list_public_cases():
        if item.case_id == normalized:
            return item
    return None


def _compose_public_case_file_name(*, display_name: str, source_file_name: str, case_id: str) -> str:
    source_name = str(source_file_name or "").strip()
    source_suffix = Path(source_name).suffix
    visible_name = str(display_name or "").strip()
    if visible_name:
        if source_suffix and visible_name.lower().endswith(source_suffix.lower()):
            return visible_name
        if source_suffix:
            return f"{visible_name}{source_suffix}"
        return visible_name
    if source_name:
        return source_name
    return case_id


def decorate_public_case_graph_file_row(
    *,
    graph_file: Dict[str, Any],
    public_case: Module4PublicCase,
) -> Dict[str, Any]:
    source_file_name = str(graph_file.get("file_name") or "").strip()
    metadata = dict(graph_file.get("metadata") or {}) if isinstance(graph_file.get("metadata"), dict) else {}
    metadata["visibility"] = "public_case"
    metadata["scope"] = "public_case"
    metadata["public_case"] = {
        "case_id": public_case.case_id,
        "display_name": public_case.display_name,
        "description": public_case.description,
        "tags": list(public_case.tags),
        "sort_order": public_case.sort_order,
        "read_only": True,
        "source_tenant_id": public_case.source_tenant_id,
        "source_file_hash": public_case.source_file_hash,
        "source_file_name": source_file_name,
    }

    decorated = dict(graph_file)
    decorated["graph_file_id"] = f"public_case:{public_case.case_id}"
    decorated["tenant_id"] = PUBLIC_CASE_LIBRARY_TENANT_ID
    decorated["file_hash"] = public_case_file_hash(public_case.case_id)
    decorated["file_name"] = _compose_public_case_file_name(
        display_name=public_case.display_name,
        source_file_name=source_file_name,
        case_id=public_case.case_id,
    )
    decorated["metadata"] = metadata
    return decorated


async def list_resolved_public_case_graph_accesses(
    *,
    storage: Any,
    asset_owner_id: str,
    status: Optional[str] = None,
) -> List[Module4ResolvedGraphAccess]:
    get_graph_file = getattr(storage, "get_graph_file", None)
    if not callable(get_graph_file):
        return []

    normalized_status = str(status or "").strip().lower() or None
    results: List[Module4ResolvedGraphAccess] = []
    for public_case in list_public_cases():
        graph_file = await get_graph_file(
            tenant_id=public_case.source_tenant_id,
            file_hash=public_case.source_file_hash,
        )
        if not graph_file:
            continue
        row_status = str(graph_file.get("status") or "").strip().lower()
        if normalized_status and row_status != normalized_status:
            continue
        results.append(
            Module4ResolvedGraphAccess(
                graph_file=dict(graph_file),
                response_graph_file=decorate_public_case_graph_file_row(
                    graph_file=dict(graph_file),
                    public_case=public_case,
                ),
                storage_tenant_id=public_case.source_tenant_id,
                asset_owner_id=str(asset_owner_id or "").strip() or PUBLIC_CASE_LIBRARY_TENANT_ID,
                requested_file_hash=public_case_file_hash(public_case.case_id),
                storage_file_hash=public_case.source_file_hash,
                public_case=public_case,
            )
        )
    return results


async def resolve_graph_file_access(
    *,
    storage: Any,
    tenant_id: str,
    file_hash: str,
) -> Optional[Module4ResolvedGraphAccess]:
    normalized_tenant = str(tenant_id or "").strip() or PUBLIC_CASE_LIBRARY_TENANT_ID
    normalized_file_hash = str(file_hash or "").strip()
    if not normalized_file_hash:
        return None

    get_graph_file = getattr(storage, "get_graph_file", None)
    if not callable(get_graph_file):
        return None

    if is_public_case_file_hash(normalized_file_hash):
        public_case = get_public_case(normalized_file_hash)
        if not public_case:
            return None
        graph_file = await get_graph_file(
            tenant_id=public_case.source_tenant_id,
            file_hash=public_case.source_file_hash,
        )
        if not graph_file:
            return None
        graph_file_row = dict(graph_file)
        return Module4ResolvedGraphAccess(
            graph_file=graph_file_row,
            response_graph_file=decorate_public_case_graph_file_row(
                graph_file=graph_file_row,
                public_case=public_case,
            ),
            storage_tenant_id=public_case.source_tenant_id,
            asset_owner_id=normalized_tenant,
            requested_file_hash=normalized_file_hash,
            storage_file_hash=public_case.source_file_hash,
            public_case=public_case,
        )

    graph_file = await get_graph_file(tenant_id=normalized_tenant, file_hash=normalized_file_hash)
    if not graph_file:
        return None
    graph_file_row = dict(graph_file)
    return Module4ResolvedGraphAccess(
        graph_file=graph_file_row,
        response_graph_file=graph_file_row,
        storage_tenant_id=normalized_tenant,
        asset_owner_id=normalized_tenant,
        requested_file_hash=normalized_file_hash,
        storage_file_hash=normalized_file_hash,
        public_case=None,
    )


__all__ = [
    "Module4PublicCase",
    "Module4ResolvedGraphAccess",
    "PUBLIC_CASE_FILE_HASH_PREFIX",
    "PUBLIC_CASE_LIBRARY_TENANT_ID",
    "decorate_public_case_graph_file_row",
    "get_public_case",
    "is_public_case_file_hash",
    "list_public_cases",
    "list_resolved_public_case_graph_accesses",
    "public_case_file_hash",
    "resolve_graph_file_access",
]
