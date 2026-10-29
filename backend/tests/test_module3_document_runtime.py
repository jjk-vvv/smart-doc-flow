from __future__ import annotations

import asyncio
import io
import os
import sys
from importlib import import_module
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


fusion_routes = import_module("app.modules.module3.api.endpoints.fusion")
source_dispatcher = import_module("app.modules.module3.services.source_dispatcher")
schema_module = import_module("app.modules.module3.schemas.run_schemas")


def _build_request(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def test_parse_word_document_json_reads_current_document_each_time(monkeypatch, tmp_path: Path) -> None:
    run_dir = (tmp_path / "run_1").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = (tmp_path / "result.docx").resolve()
    output_path.write_bytes(b"first")

    parse_calls: list[bytes] = []

    def fake_parse(path: Path) -> dict[str, object]:
        parse_calls.append(path.read_bytes())
        return {"sections": [{"id": f"section-{len(parse_calls)}"}]}

    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request: "tenant-a")
    monkeypatch.setattr(
        fusion_routes,
        "_require_docx_run_output_path",
        lambda run_id, owner_id: ({"run_id": run_id, "owner_id": owner_id}, output_path),
    )
    monkeypatch.setattr(fusion_routes, "run_directory", lambda run_id: run_dir)
    monkeypatch.setattr(fusion_routes, "parse_word_document_to_json", fake_parse)

    request = _build_request("/module3/api/v1/word/parse-json")
    payload = schema_module.WordParseRequest(run_id="run_1")

    first = fusion_routes.parse_word_document_json(request, payload)
    second = fusion_routes.parse_word_document_json(request, payload)

    assert len(parse_calls) == 2
    assert first["sections"] != second["sections"]

    output_path.write_bytes(b"second")
    os.utime(output_path, None)

    third = fusion_routes.parse_word_document_json(request, payload)

    assert len(parse_calls) == 3
    assert third["sections"] != second["sections"]


def test_save_run_output_file_replaces_document_bytes(monkeypatch, tmp_path: Path) -> None:
    run_dir = (tmp_path / "run_2").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = (tmp_path / "result.xlsx").resolve()
    output_path.write_bytes(b"before")

    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request: "tenant-a")
    monkeypatch.setattr(
        fusion_routes,
        "_require_run_output_path",
        lambda run_id, owner_id: ({"run_id": run_id, "owner_id": owner_id}, output_path),
    )
    monkeypatch.setattr(fusion_routes, "run_directory", lambda run_id: run_dir)
    monkeypatch.setattr(fusion_routes, "register_run_output_file_asset", lambda path, owner_id, filename=None: "fa_new")
    monkeypatch.setattr(
        fusion_routes,
        "set_run_status",
        lambda run_id, **updates: {"run_id": run_id, **updates},
    )

    request = _build_request("/module3/run/run_2/save-file")
    upload = UploadFile(file=io.BytesIO(b"after"), filename="result.xlsx")
    result = asyncio.run(fusion_routes.save_run_output_file("run_2", request, upload))

    assert result["status"] == "ok"
    assert output_path.read_bytes() == b"after"


def test_extract_rows_from_word_source_uses_chat_with_images(monkeypatch, tmp_path: Path) -> None:
    word_path = (tmp_path / "source.docx").resolve()
    word_path.write_bytes(b"demo")

    calls = {
        "images": 0,
        "text": 0,
        "chat": 0,
    }

    def fake_extract_docx_images(path: Path, *, max_images: int, max_image_bytes: int) -> list[dict[str, str]]:
        calls["images"] += 1
        return [{"data_url": "data:image/png;base64,AAAA", "caption": "chart"}]

    def fake_read_docx_content(path: Path) -> str:
        calls["text"] += 1
        return "Document body"


    def fake_request_chat_completions(**kwargs) -> str:
        calls["chat"] += 1
        assert kwargs["image_inputs"][0]["data_url"].startswith("data:image/png")
        return '{"rows": [{"name": "Alice"}]}'

    monkeypatch.setattr(source_dispatcher, "extract_docx_images", fake_extract_docx_images)
    monkeypatch.setattr(source_dispatcher, "read_docx_content", fake_read_docx_content)
    monkeypatch.setattr(source_dispatcher, "request_chat_completions", fake_request_chat_completions)
    monkeypatch.setattr(source_dispatcher, "_extract_rows_with_word_recall_pass", lambda **kwargs: [])


    first = source_dispatcher.extract_rows_from_word_source(
        word_path=word_path,
        headers=["name"],
        prompt="extract",
        base_url="https://example.com/v1",
        api_key="demo-key",
        model="demo-model",
        api_mode="chat",
        max_images=4,
        max_image_bytes=1024,
        logger=None,
    )
    second = source_dispatcher.extract_rows_from_word_source(
        word_path=word_path,
        headers=["name"],
        prompt="extract",
        base_url="https://example.com/v1",
        api_key="demo-key",
        model="demo-model",
        api_mode="chat",
        max_images=4,
        max_image_bytes=1024,
        logger=None,
    )

    assert first == [{"name": "Alice"}]
    assert second == first
    assert calls["images"] == 2
    assert calls["text"] == 2
    assert calls["chat"] == 2
