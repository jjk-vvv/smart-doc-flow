from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.config import DOCSETS_DIR, RUNS_DIR, TEMPLATES_DIR
from .storage_service import normalize_owner_id, read_json


def _safe_iso_from_timestamp(timestamp: float | None) -> str | None:
    if not timestamp:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp)).isoformat()
    except Exception:
        return None


def _safe_read_record(path: Path) -> dict[str, Any] | None:
    try:
        payload = read_json(path)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _record_owner_matches(record: dict[str, Any], owner_id: str) -> bool:
    return normalize_owner_id(record.get("owner_id")) == normalize_owner_id(owner_id)


def _status_bucket(raw_status: Any) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"running", "queued", "cancel_requested"}:
        return "running"
    if normalized in {"done", "completed", "success"}:
        return "done"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    return "other"


def _sort_paths_by_mtime(paths: list[Path]) -> list[Path]:
    return sorted(
        paths,
        key=lambda candidate: candidate.stat().st_mtime if candidate.exists() else 0,
        reverse=True,
    )


def _iter_owner_records(paths: list[Path], owner_id: str) -> list[tuple[Path, dict[str, Any]]]:
    output: list[tuple[Path, dict[str, Any]]] = []
    for path in _sort_paths_by_mtime(paths):
        record = _safe_read_record(path)
        if not record or not _record_owner_matches(record, owner_id):
            continue
        output.append((path, record))
    return output


def build_owner_dashboard_overview(owner_id: str, *, limit: int = 6) -> dict[str, Any]:
    normalized_owner_id = normalize_owner_id(owner_id)
    safe_limit = max(3, min(int(limit or 6), 12))

    template_records = _iter_owner_records(list(TEMPLATES_DIR.glob("*.json")), normalized_owner_id)
    docset_records = _iter_owner_records(list(DOCSETS_DIR.glob("*.json")), normalized_owner_id)
    run_records = _iter_owner_records(list(RUNS_DIR.glob("*/status.json")), normalized_owner_id)

    running_count = 0
    done_count = 0
    failed_count = 0
    cancelled_count = 0
    output_ready_count = 0

    recent_runs: list[dict[str, Any]] = []
    recent_outputs: list[dict[str, Any]] = []

    for path, record in run_records:
        status = str(record.get("status") or "").strip().lower() or "unknown"
        bucket = _status_bucket(status)
        if bucket == "running":
            running_count += 1
        elif bucket == "done":
            done_count += 1
        elif bucket == "failed":
            failed_count += 1
        elif bucket == "cancelled":
            cancelled_count += 1

        output_file_id = str(record.get("output_file_id") or "").strip()
        output_name = str(record.get("output_name") or "").strip()
        if output_file_id:
            output_ready_count += 1

        updated_at = (
            str(record.get("finished_at") or "").strip()
            or str(record.get("created_at") or "").strip()
            or _safe_iso_from_timestamp(path.stat().st_mtime)
            or ""
        )

        recent_runs.append(
            {
                "runId": str(record.get("run_id") or "").strip(),
                "status": status,
                "filled": int(record.get("filled") or 0),
                "total": int(record.get("total") or 0),
                "fillRate": float(record.get("fill_rate") or 0),
                "templateId": str(record.get("template_id") or "").strip(),
                "docSetId": str(record.get("doc_set_id") or "").strip(),
                "outputFileId": output_file_id or None,
                "outputName": output_name or None,
                "error": str(record.get("error") or "").strip() or None,
                "updatedAt": updated_at or None,
            }
        )

        if output_file_id:
            recent_outputs.append(
                {
                    "runId": str(record.get("run_id") or "").strip(),
                    "outputFileId": output_file_id,
                    "outputName": output_name or "已生成填表结果",
                    "downloadUrl": f"/download/{output_file_id}",
                    "previewUrl": f"/module3/documents/preview?file_id={output_file_id}",
                    "updatedAt": updated_at or None,
                }
            )

    active_run = next(
        (item for item in recent_runs if str(item.get("status") or "").strip().lower() in {"running", "queued", "cancel_requested"}),
        None,
    )

    return {
        "ok": True,
        "ownerId": normalized_owner_id,
        "generatedAt": datetime.now().isoformat(),
        "summary": {
            "templateCount": len(template_records),
            "docsetCount": len(docset_records),
            "runCount": len(run_records),
            "runningCount": running_count,
            "doneCount": done_count,
            "failedCount": failed_count,
            "cancelledCount": cancelled_count,
            "outputReadyCount": output_ready_count,
        },
        "activeRun": active_run,
        "recentRuns": recent_runs[:safe_limit],
        "recentOutputs": recent_outputs[:safe_limit],
    }


__all__ = ["build_owner_dashboard_overview"]
