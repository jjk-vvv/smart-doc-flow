from __future__ import annotations

from typing import Any

from .storage_service import normalize_owner_id, utcnow_iso


def create_docset_record(
    doc_set_id: str,
    files: list[dict[str, Any]],
    *,
    owner_id: str = "default",
) -> dict[str, Any]:
    return {
        "doc_set_id": doc_set_id,
        "owner_id": normalize_owner_id(owner_id),
        "count": len(files),
        "files": files,
        "created_at": utcnow_iso(),
    }


__all__ = ["create_docset_record"]
