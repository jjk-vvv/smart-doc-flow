from __future__ import annotations

from pathlib import Path


def test_module2_main_is_standard_entrypoint_without_compat_runtime_exports() -> None:
    module2_main = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "main.py"
    source = module2_main.read_text(encoding="utf-8")

    assert "from .composition.application import app, create_app" in source
    assert "__all__ = [" in source
    assert "\"app\"" in source
    assert "\"create_app\"" in source
    assert "def __getattr__(name: str):" not in source
    assert "module2_bootstrap_components = " not in source
    assert "extract_batch = " not in source
    assert "extract_cache_clear = " not in source
    assert "from .bootstrap.foundation import build_module2_default_bootstrap_components" not in source
    assert "from .runtime import build_module2_default_bootstrap_components" not in source
    assert "from .runtime.main_foundation_bundle import build_module2_default_bootstrap_components" not in source


def test_module2_composition_application_owns_main_bootstrap_assembly() -> None:
    module2_application = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "composition"
        / "application.py"
    )
    source = module2_application.read_text(encoding="utf-8")

    assert "from .foundation import build_module2_default_bootstrap_components" in source


def test_module2_foundation_builder_bootstrap_adapter_delegates_to_service_layer() -> None:
    foundation_builder = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "bootstrap"
        / "foundation_builder.py"
    )
    source = foundation_builder.read_text(encoding="utf-8")

    assert "from ..services.extraction import foundation_builder as _service_module" in source


def test_module2_foundation_bootstrap_surface_delegates_to_composition_layer() -> None:
    foundation_surface = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "bootstrap"
        / "foundation.py"
    )
    source = foundation_surface.read_text(encoding="utf-8")

    assert "from ..composition.foundation import (" in source


def test_module2_runtime_package_is_static_without_dynamic_exports() -> None:
    runtime_init = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "runtime"
        / "__init__.py"
    )
    source = runtime_init.read_text(encoding="utf-8")

    assert "def __getattr__(name: str):" not in source
    assert "build_module2_main_foundation_bundle" not in source
    assert "build_module2_main_entry_bundle" not in source
    assert "build_module2_main_service_bundle" not in source
    assert "build_module2_main_support_bundle" not in source
    assert "build_module2_main_schema_pipeline_bundle" not in source


def test_module2_foundation_service_builder_prefers_service_bundles_for_migrated_clusters() -> None:
    foundation_builder = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "services"
        / "extraction"
        / "foundation_builder.py"
    )
    source = foundation_builder.read_text(encoding="utf-8")

    assert "from .document_io_builder import Module2MainDocumentIoBundle, build_module2_main_document_io_bundle" in source
    assert "from .entry_builder import Module2MainEntryBundle, build_module2_main_entry_bundle" in source
    assert "from .extraction_builder import Module2MainExtractionBundle, build_module2_main_extraction_bundle" in source
    assert "from .geometry_builder import Module2MainGeometryBundle, build_module2_main_geometry_bundle" in source
    assert "from .nonpdf_builder import Module2MainNonPdfBundle, build_module2_main_nonpdf_bundle" in source
    assert "from .platform_builder import Module2MainPlatformBundle, build_module2_main_platform_bundle" in source
    assert "from .policy_builder import Module2MainPolicyBundle, build_module2_main_policy_bundle" in source
    assert "from .progress_builder import Module2MainProgressBundle, build_module2_main_progress_bundle" in source
    assert "from .quick_extract_builder import (" in source
    assert "from .quality_builder import Module2MainQualityBundle, build_module2_main_quality_bundle" in source
    assert "from .service_builder import Module2MainServiceBundle, build_module2_main_service_bundle" in source
    assert "from .support_builder import Module2MainSupportBundle, build_module2_main_support_bundle" in source
    assert "from .workflow_builder import Module2MainWorkflowBundle, build_module2_main_workflow_bundle" in source
    assert "from ..schema.schema_pipeline_builder import (" in source
    assert "from ..schema.schema_primitives_builder import (" in source
    assert "from ...runtime.main_document_io_bundle import" not in source
    assert "from ...runtime.main_geometry_bundle import" not in source
    assert "from ...runtime.main_nonpdf_bundle import" not in source
    assert "from ...runtime.main_platform_bundle import" not in source
    assert "from ...runtime.main_policy_bundle import" not in source
    assert "from ...runtime.main_progress_bundle import" not in source
    assert "from ...runtime.main_quick_extract_bundle import" not in source
    assert "from ...runtime.main_quality_bundle import" not in source
    assert "from ...runtime.main_workflow_bundle import" not in source
    assert "from ...runtime.main_schema_pipeline_bundle import" not in source
    assert "from ...runtime.main_schema_primitives_bundle import" not in source


def test_module2_schema_pipeline_service_builder_prefers_service_bundles_for_migrated_clusters() -> None:
    schema_pipeline_builder = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "services"
        / "schema"
        / "schema_pipeline_builder.py"
    )
    source = schema_pipeline_builder.read_text(encoding="utf-8")

    assert "from .result_filter_builder import (" in source
    assert "from .schema_context_builder import (" in source
    assert "from .schema_fields_builder import (" in source
    assert "from .schema_inference_builder import (" in source
    assert "from .schema_llm_builder import Module2MainSchemaLlmBundle, build_module2_main_schema_llm_bundle" in source
    assert "from .schema_resolution_builder import (" in source
    assert "from .schema_selection_builder import (" in source
    assert "from .schema_semantics_builder import (" in source
    assert "from ..runtime.main_result_filter_bundle import" not in source
    assert "from ..runtime.main_schema_context_bundle import" not in source
    assert "from ..runtime.main_schema_fields_bundle import" not in source
    assert "from ..runtime.main_schema_inference_bundle import" not in source
    assert "from ..runtime.main_schema_llm_bundle import" not in source
    assert "from ..runtime.main_schema_resolution_bundle import" not in source
    assert "from ..runtime.main_schema_selection_bundle import" not in source
    assert "from ..runtime.main_schema_semantics_bundle import" not in source


def test_module2_schema_subbundle_bootstrap_builders_delegate_to_service_layer() -> None:
    bootstrap_dir = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "bootstrap"
    service_import_assertions = {
        "document_io_builder.py": "from ..services.extraction import document_io_builder as _service_module",
        "entry_builder.py": "from ..services.extraction import entry_builder as _service_module",
        "extraction_builder.py": "from ..services.extraction import extraction_builder as _service_module",
        "foundation_builder.py": "from ..services.extraction import foundation_builder as _service_module",
        "geometry_builder.py": "from ..services.extraction import geometry_builder as _service_module",
        "nonpdf_builder.py": "from ..services.extraction import nonpdf_builder as _service_module",
        "platform_builder.py": "from ..services.extraction import platform_builder as _service_module",
        "policy_builder.py": "from ..services.extraction import policy_builder as _service_module",
        "progress_builder.py": "from ..services.extraction import progress_builder as _service_module",
        "quick_extract_builder.py": "from ..services.extraction import quick_extract_builder as _service_module",
        "quality_builder.py": "from ..services.extraction import quality_builder as _service_module",
        "result_filter_builder.py": "from ..services.schema import result_filter_builder as _service_module",
        "schema_context_builder.py": "from ..services.schema import schema_context_builder as _service_module",
        "schema_fields_builder.py": "from ..services.schema import schema_fields_builder as _service_module",
        "schema_inference_builder.py": "from ..services.schema import schema_inference_builder as _service_module",
        "schema_llm_builder.py": "from ..services.schema import schema_llm_builder as _service_module",
        "schema_primitives_builder.py": "from ..services.schema import schema_primitives_builder as _service_module",
        "schema_resolution_builder.py": "from ..services.schema import schema_resolution_builder as _service_module",
        "schema_selection_builder.py": "from ..services.schema import schema_selection_builder as _service_module",
        "schema_semantics_builder.py": "from ..services.schema import schema_semantics_builder as _service_module",
        "schema_pipeline_builder.py": "from ..services.schema import schema_pipeline_builder as _service_module",
        "service_builder.py": "from ..services.extraction import service_builder as _service_module",
        "support_builder.py": "from ..services.extraction import support_builder as _service_module",
    }

    for file_name, expected_import in service_import_assertions.items():
        source = (bootstrap_dir / file_name).read_text(encoding="utf-8")
        assert expected_import in source


def test_module2_legacy_shell_directory_removed() -> None:
    legacy_module2_root = Path(__file__).resolve().parents[1] / "module2"
    assert not legacy_module2_root.exists()

