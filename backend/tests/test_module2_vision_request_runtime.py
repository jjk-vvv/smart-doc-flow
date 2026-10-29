from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


vision_request_module = _load_module(
    ["app", "modules", "module2", "core", "visual", "vision_request_runtime.py"],
    "_smart_doc_flow_module2_vision_request_runtime",
)

VisionRequestRuntime = vision_request_module.VisionRequestRuntime


class _FakePixmap:
    def __init__(self, *, width: int, height: int, png_bytes: bytes):
        self.width = width
        self.height = height
        self._png_bytes = png_bytes

    def tobytes(self, fmt: str) -> bytes:
        assert fmt == "png"
        return self._png_bytes


class _FakePage:
    def __init__(self, pixmaps: list[_FakePixmap]):
        self._pixmaps = pixmaps
        self.calls: list[dict[str, Any]] = []

    def get_pixmap(self, *, matrix: Any, alpha: bool) -> _FakePixmap:
        self.calls.append({"matrix": matrix, "alpha": alpha})
        return self._pixmaps.pop(0)


class _FakeResponse:
    def __init__(self, text: str):
        self._text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._text.encode("utf-8")


def _build_runtime(**overrides: Any) -> VisionRequestRuntime:
    config: dict[str, Any] = {
        "vision_dpi": 144, "vision_max_side_px": 1000, "vision_model": "test-vision-model",
        "vision_base_url": "https://provider.test/v1", "vision_endpoint_style": "openai_chat_completions",
        "vision_timeout_sec": 25.0, "vision_max_output_tokens": 4096,
        "resolve_api_key": lambda: "test-key", "extract_json_object": lambda text: json.loads(text),
    }
    config.update(overrides)
    return VisionRequestRuntime(**config)


def test_vision_request_runtime_renders_and_downscales_large_page(monkeypatch) -> None:
    fake_fitz = types.SimpleNamespace(Matrix=lambda x, y: {"x": x, "y": y})
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    page = _FakePage(
        [
            _FakePixmap(width=2400, height=1200, png_bytes=b"first"),
            _FakePixmap(width=1000, height=500, png_bytes=b"second"),
        ]
    )
    runtime = _build_runtime()

    result = runtime.render_page_png_for_vision(page)

    assert result == b"second"
    assert len(page.calls) == 2
    assert page.calls[0]["alpha"] is False


def test_vision_request_runtime_extracts_openai_compatible_payload() -> None:
    requests_seen: list[dict[str, Any]] = []
    def request_factory(*, url: str, data: bytes, headers: dict[str, str], method: str) -> Any:
        requests_seen.append({"url": url, "headers": headers, "body": json.loads(data), "method": method})
        return types.SimpleNamespace(url=url)
    runtime = _build_runtime(
        request_factory=request_factory,
        urlopen=lambda request, timeout: _FakeResponse(json.dumps({"choices": [{"message": {"content": '{"insights":["ok"]}'}}]})),
    )
    assert runtime.extract_payload(b"fake-png", focus="table") == {"insights": ["ok"]}
    assert len(requests_seen) == 1
    request = requests_seen[0]
    assert request["url"] == "https://provider.test/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["body"]["model"] == "test-vision-model"
    assert "Extract visible table information" in request["body"]["messages"][0]["content"][0]["text"]


def test_vision_request_runtime_returns_empty_when_no_keys_available() -> None:
    runtime = _build_runtime(
        resolve_api_key=lambda: "",
    )

    assert runtime.generate(b"fake-png", focus="mixed") == ""
