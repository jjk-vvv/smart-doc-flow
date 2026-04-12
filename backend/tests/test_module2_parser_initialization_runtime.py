from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_initialization_runtime_module = import_module("module2.app.core.parsers.parser_initialization_runtime")
parser_module = import_module("module2.app.core.parser")


class _BootstrapStub:
    def build_support_runtime_attrs(self, **kwargs):
        return {"support_attr": "ok"}

    def build_provider_state_runtime(self, **kwargs):
        return {"provider_state": "ready"}


class _ParserStub:
    def __init__(self) -> None:
        self._getenv = os.getenv
        self._parser_bootstrap_runtime = _BootstrapStub()
        self._mineru_layout_extractor_factory = object()
        self._roi_cropper_factory = object()
        self._visual_vision_extractor_factory = object()

    def _mineru_layout_extractor_kwargs(self):
        return {}

    def _roi_cropper_kwargs(self):
        return {}

    def _visual_vision_extractor_kwargs(self):
        return {}


class _TrackingInitializationRuntime(parser_initialization_runtime_module.ParserInitializationRuntime):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.text_extensions: set[str] | None = None
        self.image_extensions: set[str] | None = None

    def _init_core_parse_config(self, **kwargs) -> None:
        self.calls.append("core")

    def _init_ocr_table_limits(self, **kwargs) -> None:
        self.calls.append("ocr")

    def _init_docx_media_config(self, **kwargs) -> None:
        self.calls.append("docx_media")

    def _init_table_merge_and_vision_config(self, **kwargs) -> None:
        self.calls.append("table_merge")

    def _init_visual_mineru_config(self, **kwargs) -> None:
        self.calls.append("visual_mineru")

    def _init_document_table_runtimes(self, **kwargs) -> None:
        self.calls.append("document_table")

    def _init_semantic_vision_runtimes(self, **kwargs) -> None:
        self.calls.append("semantic")

    def _init_pdf_image_runtimes(self, **kwargs) -> None:
        self.calls.append("pdf_image")

    def _init_visual_pipeline_runtimes(self, *, image_extensions, **kwargs) -> None:
        self.calls.append("visual_pipeline")
        self.image_extensions = set(image_extensions)

    def _init_docx_dispatch_runtimes(self, *, text_extensions, image_extensions, **kwargs) -> None:
        self.calls.append("docx_dispatch")
        self.text_extensions = set(text_extensions)
        self.image_extensions = set(image_extensions)


def test_parser_initialization_runtime_initializes_support_state_and_phases_in_order() -> None:
    parser = _ParserStub()
    runtime = _TrackingInitializationRuntime()

    runtime.initialize(
        parser=parser,
        max_pages=5,
        text_extensions={".txt", ".md"},
        image_extensions={".png", ".jpg"},
        limit_env_value=lambda name, default, **kwargs: default,
    )

    assert parser.support_attr == "ok"
    assert parser._parser_provider_state_runtime == {"provider_state": "ready"}
    assert runtime.calls == [
        "core",
        "ocr",
        "docx_media",
        "table_merge",
        "visual_mineru",
        "document_table",
        "semantic",
        "pdf_image",
        "visual_pipeline",
        "docx_dispatch",
    ]
    assert runtime.text_extensions == {".txt", ".md"}
    assert runtime.image_extensions == {".png", ".jpg"}


def test_native_document_parser_exposes_docx_via_pdf_compat_aliases() -> None:
    parser = parser_module.NativeDocumentParser(max_pages=1)

    assert callable(getattr(parser, "_overlay_last_parse_stats", None))
    assert callable(getattr(parser, "_merge_docx_chart_xml_into_pdf_figures", None))
