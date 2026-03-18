from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local Module 2 extraction job regression.")
    parser.add_argument("--file", required=True, help="Input document path")
    parser.add_argument("--run-dir", required=True, help="Directory to store regression outputs")
    parser.add_argument(
        "--schema-json",
        default='{"auto_infer": true, "prefer_llm": true, "max_auto_fields": 12}',
        help="Schema JSON string",
    )
    parser.add_argument("--poll-sec", type=float, default=10.0, help="Polling interval in seconds")
    parser.add_argument("--clear-cache", action="store_true", help="Clear Module 2 runtime/artifact cache first")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    module2_root = repo_root / "backend" / "module2"
    sys.path.insert(0, str(module2_root))

    from app.main import app  # noqa: WPS433

    input_path = Path(args.file).resolve()
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    schema = json.loads(args.schema_json)

    with TestClient(app) as client:
        if args.clear_cache:
            clear_resp = client.post("/extract/cache/clear")
            (run_dir / "cache_clear.json").write_text(
                json.dumps(clear_resp.json(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        with input_path.open("rb") as fh:
            create_resp = client.post(
                "/extract/jobs/create",
                files={"files": (input_path.name, fh, "application/octet-stream")},
                data={"schema": json.dumps(schema, ensure_ascii=False), "tenant_id": ""},
            )
        create_resp.raise_for_status()
        created = create_resp.json()
        (run_dir / "created.json").write_text(
            json.dumps(created, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        job_id = created["job_id"]
        started_at = time.time()
        status = created

        while True:
            poll_resp = client.get(
                f"/extract/jobs/status/{job_id}",
                params={"include_documents": "true"},
            )
            poll_resp.raise_for_status()
            status = poll_resp.json()
            (run_dir / "latest_poll.json").write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if status.get("terminal"):
                break
            time.sleep(max(1.0, args.poll_sec))

    elapsed_sec = round(time.time() - started_at, 2)
    (run_dir / "final_payload.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    doc = (status.get("documents") or [{}])[0]
    diagnostics = doc.get("diagnostics") or {}
    summary = {
        "path": str(input_path),
        "job_id": job_id,
        "status": status.get("status"),
        "terminal": status.get("terminal"),
        "elapsed_sec": elapsed_sec,
        "errors": doc.get("errors") or status.get("errors") or [],
        "soft_warnings": doc.get("soft_warnings") or [],
        "field_count": len(doc.get("result") or {}),
        "result_fields": list((doc.get("result") or {}).keys()),
        "quality_status": diagnostics.get("quality_status"),
        "quality_reasons": diagnostics.get("quality_reasons"),
        "schema_source": diagnostics.get("schema_source"),
        "schema_field_count": diagnostics.get("schema_field_count"),
        "schema_fields": diagnostics.get("schema_fields"),
        "quality_snapshot": diagnostics.get("quality_snapshot"),
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
