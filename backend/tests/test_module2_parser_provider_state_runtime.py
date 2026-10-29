from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_provider_state_runtime_module = import_module("app.modules.module2.core.parsers.parser_bootstrap_runtime")

ParserProviderStateRuntime = parser_provider_state_runtime_module.ParserProviderStateRuntime


class _FakeProvider:
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)


def test_parser_provider_state_runtime_lazily_creates_and_reuses_provider_instances() -> None:
    calls = {
        "mineru": 0,
        "cropper": 0,
        "vision": 0,
    }

    def _factory(name: str):
        def _build(**kwargs):
            calls[name] += 1
            return _FakeProvider(kind=name, **kwargs)

        return _build

    runtime = ParserProviderStateRuntime(
        mineru_layout_extractor_factory=_factory("mineru"),
        build_mineru_layout_kwargs=lambda: {"backend": "pipeline"},
        roi_cropper_factory=_factory("cropper"),
        build_roi_cropper_kwargs=lambda: {"table_dpi": 260},
        visual_vision_extractor_factory=_factory("vision"),
        build_visual_vision_kwargs=lambda: {"model": "test-vision-model"},
    )

    mineru_first = runtime.get_mineru_layout_extractor()
    mineru_second = runtime.get_mineru_layout_extractor()
    cropper_first = runtime.get_roi_cropper()
    cropper_second = runtime.get_roi_cropper()
    vision_first = runtime.get_visual_vision_extractor()
    vision_second = runtime.get_visual_vision_extractor()

    assert mineru_first is mineru_second
    assert cropper_first is cropper_second
    assert vision_first is vision_second
    assert mineru_first.kwargs == {"kind": "mineru", "backend": "pipeline"}
    assert cropper_first.kwargs == {"kind": "cropper", "table_dpi": 260}
    assert vision_first.kwargs == {"kind": "vision", "model": "test-vision-model"}
    assert calls == {
        "mineru": 1,
        "cropper": 1,
        "vision": 1,
    }


def test_parser_provider_state_runtime_reset_drops_cached_instances() -> None:
    counter = {"value": 0}

    def _factory(**kwargs):
        counter["value"] += 1
        return _FakeProvider(seq=counter["value"], **kwargs)

    runtime = ParserProviderStateRuntime(
        mineru_layout_extractor_factory=_factory,
        build_mineru_layout_kwargs=lambda: {"backend": "pipeline"},
        roi_cropper_factory=_factory,
        build_roi_cropper_kwargs=lambda: {"table_dpi": 260},
        visual_vision_extractor_factory=_factory,
        build_visual_vision_kwargs=lambda: {"model": "test-vision-model"},
    )

    first = runtime.get_mineru_layout_extractor()
    runtime.reset()
    second = runtime.get_mineru_layout_extractor()

    assert first is not second
    assert first.kwargs["seq"] == 1
    assert second.kwargs["seq"] == 2
