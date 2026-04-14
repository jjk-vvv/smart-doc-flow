from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


storage_service = import_module("app.modules.module3.services.storage_service")


def test_load_run_record_does_not_backfill_legacy_output_path(monkeypatch, tmp_path: Path) -> None:
    output_path = (tmp_path / "result.xlsx").resolve()
    output_path.write_bytes(b"legacy")

    status_path = (tmp_path / "status.json").resolve()
    status_payload = {
        "run_id": "run_legacy",
        "owner_id": "tenant-a",
        "status": "done",
        "filled": 1,
        "total": 1,
        "fill_rate": 1.0,
        "output_filename": str(output_path),
        "output_file_id": None,
        "template_id": "tpl_1",
        "doc_set_id": "doc_1",
    }
    status_path.write_text(json.dumps(status_payload, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(storage_service, "database_enabled", lambda: False)
    monkeypatch.setattr(storage_service, "run_status_path", lambda run_id: status_path)
    monkeypatch.setattr(storage_service, "run_log_path", lambda run_id: (tmp_path / "run.log"))
    record = storage_service.load_run_record("run_legacy", owner_id="tenant-a")

    assert not record.get("output_file_id")
    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert not persisted.get("output_file_id")
