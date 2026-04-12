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
    ["module2", "app", "core", "visual", "vision_request_runtime.py"],
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
        "gemini_vision_dpi": 144,
        "gemini_vision_max_side_px": 1000,
        "gemini_vision_model": "gemini-3.1-pro-preview",
        "gemini_vision_timeout_sec": 25.0,
        "gemini_vision_max_output_tokens": 4096,
        "gemini_native_fallback_enabled": True,
        "resolve_api_key": lambda: "primary-token",
        "resolve_native_api_key": lambda: "AIza-native-key",
        "resolve_native_url": lambda model: f"https://proxy.test/v1beta/models/{model}:generateContent",
        "build_google_native_url": lambda model: f"https://google.test/v1beta/models/{model}:generateContent",
        "build_headers": lambda url, key: {"Authorization": f"Bearer {key}", "X-Url": url},
        "extract_json_object": lambda text: json.loads(text),
        "extract_candidate_text": lambda raw: json.loads(raw)["text"],
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


def test_vision_request_runtime_extracts_payload_with_fallback_request() -> None:
    requests_seen: list[dict[str, Any]] = []

    def _request_factory(*, url: str, data: bytes, headers: dict[str, str], method: str) -> Any:
        payload = json.loads(data.decode("utf-8"))
        requests_seen.append(
            {
                "url": url,
                "headers": dict(headers),
                "method": method,
                "prompt": payload["contents"][0]["parts"][0]["text"],
            }
        )
        return types.SimpleNamespace(url=url, data=data, headers=headers, method=method)

    def _urlopen(request: Any, timeout: float) -> _FakeResponse:
        if "proxy.test" in request.url:
            raise RuntimeError("primary failed")
        return _FakeResponse(json.dumps({"text": json.dumps({"insights": ["ok"]}, ensure_ascii=False)}))

    runtime = _build_runtime(
        request_factory=_request_factory,
        urlopen=_urlopen,
    )

    payload = runtime.extract_payload(b"fake-png", focus="table")

    assert payload == {"insights": ["ok"]}
    assert len(requests_seen) == 2
    assert requests_seen[0]["url"].startswith("https://proxy.test")
    assert requests_seen[1]["url"].startswith("https://google.test")
    assert "Extract visible table information" in requests_seen[1]["prompt"]


def test_vision_request_runtime_returns_empty_when_no_keys_available() -> None:
    runtime = _build_runtime(
        resolve_api_key=lambda: "",
        resolve_native_api_key=lambda: "",
    )

    assert runtime.generate(b"fake-png", focus="mixed") == ""
