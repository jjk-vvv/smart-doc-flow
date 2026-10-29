from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


parser_bootstrap_runtime_module = import_module("app.modules.module2.core.parsers.parser_bootstrap_runtime")
ParserBootstrapRuntime = parser_bootstrap_runtime_module.ParserBootstrapRuntime
ParserProviderStateRuntime = parser_bootstrap_runtime_module.ParserProviderStateRuntime


def test_parser_bootstrap_runtime_builds_support_runtime_attrs() -> None:
    runtime = ParserBootstrapRuntime()

    attrs = runtime.build_support_runtime_attrs(
        getenv=lambda name, default=None: default,
        limit_env_value=lambda *args, **kwargs: 1,
        module2_root=Path("module2"),
        repo_root=Path("repo"),
    )

    expected_keys = {
        "_parser_config_runtime",
        "_parser_ocr_table_inference_bundle_runtime",
        "_parser_provider_bundle_runtime",
        "_parser_image_bundle_runtime",
        "_parser_image_bootstrap_runtime",
        "_parser_dispatch_bundle_runtime",
        "_parser_docx_bootstrap_runtime",
        "_parser_docx_content_bundle_runtime",
        "_parser_document_table_bootstrap_runtime",
        "_parser_docx_pdf_entry_runtime",
        "_parser_nonpdf_entry_runtime",
        "_parser_pdf_bootstrap_runtime",
        "_parser_pdf_entry_runtime",
        "_parser_vision_bundle_runtime",
        "_parser_vision_transport_bootstrap_runtime",
        "_parser_visual_payload_bootstrap_runtime",
        "_parser_visual_payload_bundle_runtime",
        "_parser_visual_context_bootstrap_runtime",
        "_parser_visual_context_bundle_runtime",
        "_parser_visual_execution_bootstrap_runtime",
        "_parser_visual_execution_bundle_runtime",
        "_parser_semantic_bootstrap_runtime",
        "_parser_semantic_foundation_bundle_runtime",
    }

    assert set(attrs) == expected_keys
    assert hasattr(attrs["_parser_config_runtime"], "build_core_parse_config")
    assert hasattr(attrs["_parser_document_table_bootstrap_runtime"], "build_document_table_runtime_attrs")
    assert hasattr(attrs["_parser_docx_pdf_entry_runtime"], "parse_docx_via_pdf")
    assert hasattr(attrs["_parser_docx_bootstrap_runtime"], "build_docx_runtime_attrs")
    assert hasattr(attrs["_parser_nonpdf_entry_runtime"], "parse_plain")
    assert hasattr(attrs["_parser_pdf_bootstrap_runtime"], "build_pdf_runtime_attrs")
    assert hasattr(attrs["_parser_pdf_entry_runtime"], "parse_pdf")
    assert hasattr(attrs["_parser_vision_transport_bootstrap_runtime"], "build_vision_transport_runtime_attrs")
    assert hasattr(attrs["_parser_image_bootstrap_runtime"], "build_image_runtime_attrs")
    assert hasattr(attrs["_parser_visual_payload_bootstrap_runtime"], "build_visual_payload_runtime_attrs")
    assert hasattr(attrs["_parser_visual_context_bootstrap_runtime"], "build_visual_context_runtime_attrs")
    assert hasattr(attrs["_parser_visual_execution_bootstrap_runtime"], "build_visual_execution_runtime_attrs")
    assert hasattr(attrs["_parser_semantic_bootstrap_runtime"], "build_semantic_runtime_attrs")


def test_parser_bootstrap_runtime_builds_provider_state_runtime() -> None:
    runtime = ParserBootstrapRuntime()
    calls: dict[str, object] = {}

    provider_state = runtime.build_provider_state_runtime(
        mineru_layout_extractor_factory=lambda **kwargs: calls.setdefault("mineru", kwargs) or {"kind": "mineru"},
        build_mineru_layout_kwargs=lambda: {"backend": "pipeline"},
        roi_cropper_factory=lambda **kwargs: calls.setdefault("roi", kwargs) or {"kind": "roi"},
        build_roi_cropper_kwargs=lambda: {"table_dpi": 144},
        visual_vision_extractor_factory=lambda **kwargs: calls.setdefault("vision", kwargs) or {"kind": "vision"},
        build_visual_vision_kwargs=lambda: {"model": "test-chat-model"},
    )

    assert isinstance(provider_state, ParserProviderStateRuntime)
    provider_state.get_mineru_layout_extractor()
    provider_state.get_roi_cropper()
    provider_state.get_visual_vision_extractor()

    assert calls["mineru"] == {"backend": "pipeline"}
    assert calls["roi"] == {"table_dpi": 144}
    assert calls["vision"] == {"model": "test-chat-model"}
