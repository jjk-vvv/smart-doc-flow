from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


source_dispatcher = import_module("app.modules.module3.services.source_dispatcher")
user_rule_service = import_module("app.modules.module3.services.user_rule_service")


def test_extract_rows_from_word_source_skips_recall_for_high_confidence_primary_rows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    word_path = (tmp_path / "source.docx").resolve()
    word_path.write_bytes(b"demo")
    headers = ["name", "city", "gdp", "population", "budget"]
    logs: list[str] = []
    calls = {"chat": 0}

    def fake_extract_docx_images(path: Path, *, max_images: int, max_image_bytes: int) -> list[dict[str, str]]:
        return [{"data_url": "data:image/png;base64,AAAA", "caption": "chart"}]

    def fake_read_docx_content(path: Path) -> str:
        return "Document body\nMore content"


    def fake_request_chat_completions(**kwargs) -> str:
        calls["chat"] += 1
        rows = [
            {header: f"{header}-{idx}" for header in headers}
            for idx in range(60)
        ]
        return json.dumps({"rows": rows}, ensure_ascii=False)

    monkeypatch.setattr(source_dispatcher, "extract_docx_images", fake_extract_docx_images)
    monkeypatch.setattr(source_dispatcher, "read_docx_content", fake_read_docx_content)
    monkeypatch.setattr(source_dispatcher, "request_chat_completions", fake_request_chat_completions)

    rows = source_dispatcher.extract_rows_from_word_source(
        word_path=word_path,
        headers=headers,
        prompt="extract",
        base_url="https://example.com/v1",
        api_key="demo-key",
        model="demo-model",
        api_mode="chat",
        max_images=4,
        max_image_bytes=1024,
        logger=logs.append,
    )

    assert len(rows) == 60
    assert calls["chat"] == 1
    assert any("[recall skipped] high-confidence primary extraction" in entry for entry in logs)


def test_extract_rows_from_word_source_keeps_recall_for_small_primary_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    word_path = (tmp_path / "source.docx").resolve()
    word_path.write_bytes(b"demo")
    headers = ["name", "city", "gdp"]
    logs: list[str] = []
    calls = {"chat": 0}

    def fake_extract_docx_images(path: Path, *, max_images: int, max_image_bytes: int) -> list[dict[str, str]]:
        return [{"data_url": "data:image/png;base64,AAAA", "caption": "chart"}]

    def fake_read_docx_content(path: Path) -> str:
        return "Document body\nMore content"


    def fake_request_chat_completions(**kwargs) -> str:
        calls["chat"] += 1
        rows = [{"name": "Alice", "city": "Shanghai", "gdp": "100"}]
        return json.dumps({"rows": rows}, ensure_ascii=False)

    monkeypatch.setattr(source_dispatcher, "extract_docx_images", fake_extract_docx_images)
    monkeypatch.setattr(source_dispatcher, "read_docx_content", fake_read_docx_content)
    monkeypatch.setattr(source_dispatcher, "request_chat_completions", fake_request_chat_completions)

    rows = source_dispatcher.extract_rows_from_word_source(
        word_path=word_path,
        headers=headers,
        prompt="extract",
        base_url="https://example.com/v1",
        api_key="demo-key",
        model="demo-model",
        api_mode="chat",
        max_images=4,
        max_image_bytes=1024,
        logger=logs.append,
    )

    assert rows == [{"name": "Alice", "city": "Shanghai", "gdp": "100"}]
    assert calls["chat"] == 2
    assert any("[recall] running Word completeness pass" in entry for entry in logs)


def test_resolve_user_rule_bundle_skips_generic_fill_prompt_without_model_calls(monkeypatch) -> None:
    logs: list[str] = []

    def fail_request(**kwargs):
        raise AssertionError("generic fill prompt should not call the model")

    monkeypatch.setattr(user_rule_service, "request_chat_completions", fail_request)

    bundle = user_rule_service.resolve_user_rule_bundle(
        user_prompt="帮我智能填表",
        headers=["城市名"],
        settings={
            "api_mode": "chat",
            "base_url": "https://example.com/v1",
            "api_key": "demo-key",
            "model": "demo-model",
        },
        logger=logs.append,
        sample_rows=[],
    )

    assert bundle["ignore"] is True
    assert bundle["ignore_reason"] == "generic fill prompt"
    assert bundle["extraction_prompt"] == user_rule_service.DEFAULT_PROMPT
    assert any("[user rules] ignored: generic fill prompt" in entry for entry in logs)
