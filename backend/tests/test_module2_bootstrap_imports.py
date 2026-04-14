from __future__ import annotations

from importlib import import_module


def test_module2_bootstrap_foundation_exports_runtime_builders() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.foundation")
    runtime_module = import_module("app.modules.module2.runtime.main_foundation_bundle")

    assert (
        package_module.build_module2_default_bootstrap_components
        is bootstrap_module.build_module2_default_bootstrap_components
    )
    assert (
        bootstrap_module.build_module2_default_bootstrap_components
        is runtime_module.build_module2_default_bootstrap_components
    )
    assert (
        bootstrap_module.build_module2_main_foundation_bundle
        is runtime_module.build_module2_main_foundation_bundle
    )


def test_module2_bootstrap_foundation_surface_delegates_to_composition_layer() -> None:
    bootstrap_module = import_module("app.modules.module2.bootstrap.foundation")
    composition_module = import_module("app.modules.module2.composition.foundation")

    assert (
        bootstrap_module.build_module2_main_foundation_bundle
        is composition_module.build_module2_main_foundation_bundle
    )
    assert (
        bootstrap_module.build_module2_default_bootstrap_components
        is composition_module.build_module2_default_bootstrap_components
    )


def test_module2_bootstrap_foundation_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.foundation_builder")
    service_builder = import_module("app.modules.module2.services.extraction.foundation_builder")

    assert (
        bootstrap_builder.build_module2_main_foundation_bundle
        is service_builder.build_module2_main_foundation_bundle
    )
    assert (
        bootstrap_builder.build_module2_default_bootstrap_components
        is service_builder.build_module2_default_bootstrap_components
    )


def test_module2_bootstrap_entry_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.entry")
    runtime_module = import_module("app.modules.module2.runtime.main_entry_bundle")

    assert (
        package_module.build_module2_main_entry_bundle
        is bootstrap_module.build_module2_main_entry_bundle
    )
    assert (
        bootstrap_module.build_module2_main_entry_bundle
        is runtime_module.build_module2_main_entry_bundle
    )


def test_module2_bootstrap_entry_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.entry_builder")
    service_builder = import_module("app.modules.module2.services.extraction.entry_builder")

    assert (
        bootstrap_builder.build_module2_main_entry_bundle
        is service_builder.build_module2_main_entry_bundle
    )


def test_module2_runtime_package_lazy_exports_bootstrap_builders() -> None:
    runtime_package = import_module("app.modules.module2.runtime")
    foundation_module = import_module("app.modules.module2.bootstrap.foundation")
    entry_module = import_module("app.modules.module2.bootstrap.entry")
    extraction_module = import_module("app.modules.module2.bootstrap.extraction")
    document_io_module = import_module("app.modules.module2.bootstrap.document_io")
    geometry_module = import_module("app.modules.module2.bootstrap.geometry")
    nonpdf_module = import_module("app.modules.module2.bootstrap.nonpdf")
    platform_module = import_module("app.modules.module2.bootstrap.platform")
    policy_module = import_module("app.modules.module2.bootstrap.policy")
    progress_module = import_module("app.modules.module2.bootstrap.progress")
    quick_extract_module = import_module("app.modules.module2.bootstrap.quick_extract")
    quality_module = import_module("app.modules.module2.bootstrap.quality")
    result_filter_module = import_module("app.modules.module2.bootstrap.result_filter")
    schema_context_module = import_module("app.modules.module2.bootstrap.schema_context")
    schema_fields_module = import_module("app.modules.module2.bootstrap.schema_fields")
    schema_inference_module = import_module("app.modules.module2.bootstrap.schema_inference")
    schema_llm_module = import_module("app.modules.module2.bootstrap.schema_llm")
    schema_pipeline_module = import_module("app.modules.module2.bootstrap.schema_pipeline")
    schema_primitives_module = import_module("app.modules.module2.bootstrap.schema_primitives")
    schema_resolution_module = import_module("app.modules.module2.bootstrap.schema_resolution")
    schema_selection_module = import_module("app.modules.module2.bootstrap.schema_selection")
    schema_semantics_module = import_module("app.modules.module2.bootstrap.schema_semantics")
    service_module = import_module("app.modules.module2.bootstrap.service")
    support_module = import_module("app.modules.module2.bootstrap.support")

    assert (
        runtime_package.build_module2_default_bootstrap_components
        is foundation_module.build_module2_default_bootstrap_components
    )
    assert (
        runtime_package.build_module2_main_entry_bundle
        is entry_module.build_module2_main_entry_bundle
    )
    assert (
        runtime_package.build_module2_main_extraction_bundle
        is extraction_module.build_module2_main_extraction_bundle
    )
    assert (
        runtime_package.build_module2_main_document_io_bundle
        is document_io_module.build_module2_main_document_io_bundle
    )
    assert (
        runtime_package.build_module2_main_geometry_bundle
        is geometry_module.build_module2_main_geometry_bundle
    )
    assert (
        runtime_package.build_module2_main_nonpdf_bundle
        is nonpdf_module.build_module2_main_nonpdf_bundle
    )
    assert (
        runtime_package.build_module2_main_platform_bundle
        is platform_module.build_module2_main_platform_bundle
    )
    assert (
        runtime_package.build_module2_main_policy_bundle
        is policy_module.build_module2_main_policy_bundle
    )
    assert (
        runtime_package.build_module2_main_progress_bundle
        is progress_module.build_module2_main_progress_bundle
    )
    assert (
        runtime_package.build_module2_main_quick_extract_bundle
        is quick_extract_module.build_module2_main_quick_extract_bundle
    )
    assert (
        runtime_package.build_module2_main_value_guard_bundle
        is quick_extract_module.build_module2_main_value_guard_bundle
    )
    assert (
        runtime_package.build_module2_main_quality_bundle
        is quality_module.build_module2_main_quality_bundle
    )
    assert (
        runtime_package.build_module2_main_result_filter_bundle
        is result_filter_module.build_module2_main_result_filter_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_context_bundle
        is schema_context_module.build_module2_main_schema_context_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_fields_bundle
        is schema_fields_module.build_module2_main_schema_fields_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_inference_bundle
        is schema_inference_module.build_module2_main_schema_inference_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_llm_bundle
        is schema_llm_module.build_module2_main_schema_llm_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_pipeline_bundle
        is schema_pipeline_module.build_module2_main_schema_pipeline_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_pipeline_bundle_from_rules
        is schema_pipeline_module.build_module2_main_schema_pipeline_bundle_from_rules
    )
    assert (
        runtime_package.build_module2_main_schema_primitives_bundle
        is schema_primitives_module.build_module2_main_schema_primitives_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_request_bundle
        is schema_primitives_module.build_module2_main_schema_request_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_timeout_bundle
        is schema_primitives_module.build_module2_main_schema_timeout_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_resolution_bundle
        is schema_resolution_module.build_module2_main_schema_resolution_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_selection_bundle
        is schema_selection_module.build_module2_main_schema_selection_bundle
    )
    assert (
        runtime_package.build_module2_main_schema_semantics_bundle
        is schema_semantics_module.build_module2_main_schema_semantics_bundle
    )
    assert (
        runtime_package.build_module2_main_service_bundle
        is service_module.build_module2_main_service_bundle
    )
    assert (
        runtime_package.build_module2_main_support_bundle
        is support_module.build_module2_main_support_bundle
    )
    assert (
        runtime_package.build_module2_bootstrap_runtime_bundle
        is support_module.build_module2_bootstrap_runtime_bundle
    )


def test_module2_bootstrap_extraction_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.extraction")
    runtime_module = import_module("app.modules.module2.runtime.main_extraction_bundle")

    assert (
        package_module.build_module2_main_extraction_bundle
        is bootstrap_module.build_module2_main_extraction_bundle
    )
    assert (
        bootstrap_module.build_module2_main_extraction_bundle
        is runtime_module.build_module2_main_extraction_bundle
    )


def test_module2_bootstrap_extraction_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.extraction_builder")
    service_builder = import_module("app.modules.module2.services.extraction.extraction_builder")

    assert (
        bootstrap_builder.build_module2_main_extraction_bundle
        is service_builder.build_module2_main_extraction_bundle
    )
    assert (
        bootstrap_builder._EXTRACTION_RUNTIME_FINGERPRINT_FILES
        is service_builder._EXTRACTION_RUNTIME_FINGERPRINT_FILES
    )


def test_module2_bootstrap_document_io_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.document_io")
    runtime_module = import_module("app.modules.module2.runtime.main_document_io_bundle")

    assert (
        package_module.build_module2_main_document_io_bundle
        is bootstrap_module.build_module2_main_document_io_bundle
    )
    assert (
        bootstrap_module.build_module2_main_document_io_bundle
        is runtime_module.build_module2_main_document_io_bundle
    )


def test_module2_bootstrap_document_io_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.document_io_builder")
    service_builder = import_module("app.modules.module2.services.extraction.document_io_builder")

    assert (
        bootstrap_builder.build_module2_main_document_io_bundle
        is service_builder.build_module2_main_document_io_bundle
    )


def test_module2_bootstrap_geometry_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.geometry")
    runtime_module = import_module("app.modules.module2.runtime.main_geometry_bundle")

    assert (
        package_module.build_module2_main_geometry_bundle
        is bootstrap_module.build_module2_main_geometry_bundle
    )
    assert (
        bootstrap_module.build_module2_main_geometry_bundle
        is runtime_module.build_module2_main_geometry_bundle
    )


def test_module2_bootstrap_geometry_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.geometry_builder")
    service_builder = import_module("app.modules.module2.services.extraction.geometry_builder")

    assert (
        bootstrap_builder.build_module2_main_geometry_bundle
        is service_builder.build_module2_main_geometry_bundle
    )


def test_module2_bootstrap_nonpdf_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.nonpdf")
    runtime_module = import_module("app.modules.module2.runtime.main_nonpdf_bundle")

    assert (
        package_module.build_module2_main_nonpdf_bundle
        is bootstrap_module.build_module2_main_nonpdf_bundle
    )
    assert (
        bootstrap_module.build_module2_main_nonpdf_bundle
        is runtime_module.build_module2_main_nonpdf_bundle
    )


def test_module2_bootstrap_nonpdf_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.nonpdf_builder")
    service_builder = import_module("app.modules.module2.services.extraction.nonpdf_builder")

    assert (
        bootstrap_builder.build_module2_main_nonpdf_bundle
        is service_builder.build_module2_main_nonpdf_bundle
    )


def test_module2_bootstrap_platform_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.platform")
    runtime_module = import_module("app.modules.module2.runtime.main_platform_bundle")

    assert (
        package_module.build_module2_main_platform_bundle
        is bootstrap_module.build_module2_main_platform_bundle
    )
    assert (
        bootstrap_module.build_module2_main_platform_bundle
        is runtime_module.build_module2_main_platform_bundle
    )


def test_module2_bootstrap_platform_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.platform_builder")
    service_builder = import_module("app.modules.module2.services.extraction.platform_builder")

    assert (
        bootstrap_builder.build_module2_main_platform_bundle
        is service_builder.build_module2_main_platform_bundle
    )


def test_module2_bootstrap_policy_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.policy")
    runtime_module = import_module("app.modules.module2.runtime.main_policy_bundle")

    assert (
        package_module.build_module2_main_policy_bundle
        is bootstrap_module.build_module2_main_policy_bundle
    )
    assert (
        bootstrap_module.build_module2_main_policy_bundle
        is runtime_module.build_module2_main_policy_bundle
    )


def test_module2_bootstrap_policy_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.policy_builder")
    service_builder = import_module("app.modules.module2.services.extraction.policy_builder")

    assert (
        bootstrap_builder.build_module2_main_policy_bundle
        is service_builder.build_module2_main_policy_bundle
    )


def test_module2_bootstrap_progress_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.progress")
    runtime_module = import_module("app.modules.module2.runtime.main_progress_bundle")

    assert (
        package_module.build_module2_main_progress_bundle
        is bootstrap_module.build_module2_main_progress_bundle
    )
    assert (
        bootstrap_module.build_module2_main_progress_bundle
        is runtime_module.build_module2_main_progress_bundle
    )


def test_module2_bootstrap_progress_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.progress_builder")
    service_builder = import_module("app.modules.module2.services.extraction.progress_builder")

    assert (
        bootstrap_builder.build_module2_main_progress_bundle
        is service_builder.build_module2_main_progress_bundle
    )


def test_module2_bootstrap_quick_extract_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.quick_extract")
    runtime_module = import_module("app.modules.module2.runtime.main_quick_extract_bundle")

    assert (
        package_module.build_module2_main_quick_extract_bundle
        is bootstrap_module.build_module2_main_quick_extract_bundle
    )
    assert (
        package_module.build_module2_main_value_guard_bundle
        is bootstrap_module.build_module2_main_value_guard_bundle
    )
    assert (
        bootstrap_module.build_module2_main_quick_extract_bundle
        is runtime_module.build_module2_main_quick_extract_bundle
    )
    assert (
        bootstrap_module.build_module2_main_value_guard_bundle
        is runtime_module.build_module2_main_value_guard_bundle
    )


def test_module2_bootstrap_quick_extract_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.quick_extract_builder")
    service_builder = import_module("app.modules.module2.services.extraction.quick_extract_builder")

    assert (
        bootstrap_builder.build_module2_main_quick_extract_bundle
        is service_builder.build_module2_main_quick_extract_bundle
    )
    assert (
        bootstrap_builder.build_module2_main_value_guard_bundle
        is service_builder.build_module2_main_value_guard_bundle
    )


def test_module2_bootstrap_quality_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.quality")
    runtime_module = import_module("app.modules.module2.runtime.main_quality_bundle")

    assert (
        package_module.build_module2_main_quality_bundle
        is bootstrap_module.build_module2_main_quality_bundle
    )
    assert (
        bootstrap_module.build_module2_main_quality_bundle
        is runtime_module.build_module2_main_quality_bundle
    )


def test_module2_bootstrap_quality_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.quality_builder")
    service_builder = import_module("app.modules.module2.services.extraction.quality_builder")

    assert (
        bootstrap_builder.build_module2_main_quality_bundle
        is service_builder.build_module2_main_quality_bundle
    )


def test_module2_bootstrap_schema_primitives_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.schema_primitives")
    runtime_module = import_module("app.modules.module2.runtime.main_schema_primitives_bundle")

    assert (
        package_module.build_module2_main_schema_primitives_bundle
        is bootstrap_module.build_module2_main_schema_primitives_bundle
    )
    assert (
        package_module.build_module2_main_schema_request_bundle
        is bootstrap_module.build_module2_main_schema_request_bundle
    )
    assert (
        package_module.build_module2_main_schema_timeout_bundle
        is bootstrap_module.build_module2_main_schema_timeout_bundle
    )
    assert (
        bootstrap_module.build_module2_main_schema_primitives_bundle
        is runtime_module.build_module2_main_schema_primitives_bundle
    )
    assert (
        bootstrap_module.build_module2_main_schema_request_bundle
        is runtime_module.build_module2_main_schema_request_bundle
    )
    assert (
        bootstrap_module.build_module2_main_schema_timeout_bundle
        is runtime_module.build_module2_main_schema_timeout_bundle
    )


def test_module2_bootstrap_schema_pipeline_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.schema_pipeline")
    runtime_module = import_module("app.modules.module2.runtime.main_schema_pipeline_bundle")

    assert (
        package_module.build_module2_main_schema_pipeline_bundle
        is bootstrap_module.build_module2_main_schema_pipeline_bundle
    )
    assert (
        package_module.build_module2_main_schema_pipeline_bundle_from_rules
        is bootstrap_module.build_module2_main_schema_pipeline_bundle_from_rules
    )
    assert (
        bootstrap_module.build_module2_main_schema_pipeline_bundle
        is runtime_module.build_module2_main_schema_pipeline_bundle
    )
    assert (
        bootstrap_module.build_module2_main_schema_pipeline_bundle_from_rules
        is runtime_module.build_module2_main_schema_pipeline_bundle_from_rules
    )


def test_module2_bootstrap_schema_subbundle_exports_runtime_builder_shims() -> None:
    package_module = import_module("app.modules.module2.bootstrap")

    result_filter_bootstrap = import_module("app.modules.module2.bootstrap.result_filter")
    result_filter_runtime = import_module("app.modules.module2.runtime.main_result_filter_bundle")
    assert (
        package_module.build_module2_main_result_filter_bundle
        is result_filter_bootstrap.build_module2_main_result_filter_bundle
    )
    assert (
        result_filter_bootstrap.build_module2_main_result_filter_bundle
        is result_filter_runtime.build_module2_main_result_filter_bundle
    )

    schema_context_bootstrap = import_module("app.modules.module2.bootstrap.schema_context")
    schema_context_runtime = import_module("app.modules.module2.runtime.main_schema_context_bundle")
    assert (
        package_module.build_module2_main_schema_context_bundle
        is schema_context_bootstrap.build_module2_main_schema_context_bundle
    )
    assert (
        schema_context_bootstrap.build_module2_main_schema_context_bundle
        is schema_context_runtime.build_module2_main_schema_context_bundle
    )

    schema_fields_bootstrap = import_module("app.modules.module2.bootstrap.schema_fields")
    schema_fields_runtime = import_module("app.modules.module2.runtime.main_schema_fields_bundle")
    assert (
        package_module.build_module2_main_schema_fields_bundle
        is schema_fields_bootstrap.build_module2_main_schema_fields_bundle
    )
    assert (
        schema_fields_bootstrap.build_module2_main_schema_fields_bundle
        is schema_fields_runtime.build_module2_main_schema_fields_bundle
    )

    schema_inference_bootstrap = import_module("app.modules.module2.bootstrap.schema_inference")
    schema_inference_runtime = import_module("app.modules.module2.runtime.main_schema_inference_bundle")
    assert (
        package_module.build_module2_main_schema_inference_bundle
        is schema_inference_bootstrap.build_module2_main_schema_inference_bundle
    )
    assert (
        schema_inference_bootstrap.build_module2_main_schema_inference_bundle
        is schema_inference_runtime.build_module2_main_schema_inference_bundle
    )

    schema_llm_bootstrap = import_module("app.modules.module2.bootstrap.schema_llm")
    schema_llm_runtime = import_module("app.modules.module2.runtime.main_schema_llm_bundle")
    assert (
        package_module.build_module2_main_schema_llm_bundle
        is schema_llm_bootstrap.build_module2_main_schema_llm_bundle
    )
    assert (
        schema_llm_bootstrap.build_module2_main_schema_llm_bundle
        is schema_llm_runtime.build_module2_main_schema_llm_bundle
    )

    schema_semantics_bootstrap = import_module("app.modules.module2.bootstrap.schema_semantics")
    schema_semantics_runtime = import_module("app.modules.module2.runtime.main_schema_semantics_bundle")
    assert (
        package_module.build_module2_main_schema_semantics_bundle
        is schema_semantics_bootstrap.build_module2_main_schema_semantics_bundle
    )
    assert (
        schema_semantics_bootstrap.build_module2_main_schema_semantics_bundle
        is schema_semantics_runtime.build_module2_main_schema_semantics_bundle
    )

    schema_selection_bootstrap = import_module("app.modules.module2.bootstrap.schema_selection")
    schema_selection_runtime = import_module("app.modules.module2.runtime.main_schema_selection_bundle")
    assert (
        package_module.build_module2_main_schema_selection_bundle
        is schema_selection_bootstrap.build_module2_main_schema_selection_bundle
    )
    assert (
        schema_selection_bootstrap.build_module2_main_schema_selection_bundle
        is schema_selection_runtime.build_module2_main_schema_selection_bundle
    )

    schema_resolution_bootstrap = import_module("app.modules.module2.bootstrap.schema_resolution")
    schema_resolution_runtime = import_module("app.modules.module2.runtime.main_schema_resolution_bundle")
    assert (
        package_module.build_module2_main_schema_resolution_bundle
        is schema_resolution_bootstrap.build_module2_main_schema_resolution_bundle
    )
    assert (
        schema_resolution_bootstrap.build_module2_main_schema_resolution_bundle
        is schema_resolution_runtime.build_module2_main_schema_resolution_bundle
    )


def test_module2_bootstrap_service_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.service")
    runtime_module = import_module("app.modules.module2.runtime.main_service_bundle")

    assert (
        package_module.build_module2_main_service_bundle
        is bootstrap_module.build_module2_main_service_bundle
    )
    assert (
        bootstrap_module.build_module2_main_service_bundle
        is runtime_module.build_module2_main_service_bundle
    )


def test_module2_bootstrap_service_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.service_builder")
    service_builder = import_module("app.modules.module2.services.extraction.service_builder")

    assert (
        bootstrap_builder.build_module2_main_service_bundle
        is service_builder.build_module2_main_service_bundle
    )


def test_module2_bootstrap_support_exports_runtime_builder_shim() -> None:
    package_module = import_module("app.modules.module2.bootstrap")
    bootstrap_module = import_module("app.modules.module2.bootstrap.support")
    runtime_module = import_module("app.modules.module2.runtime.main_support_bundle")

    assert (
        package_module.build_module2_main_support_bundle
        is bootstrap_module.build_module2_main_support_bundle
    )
    assert (
        package_module.build_module2_bootstrap_runtime_bundle
        is bootstrap_module.build_module2_bootstrap_runtime_bundle
    )
    assert (
        bootstrap_module.build_module2_main_support_bundle
        is runtime_module.build_module2_main_support_bundle
    )
    assert (
        bootstrap_module.build_module2_bootstrap_runtime_bundle
        is runtime_module.build_module2_bootstrap_runtime_bundle
    )


def test_module2_bootstrap_support_builder_delegates_to_service_layer() -> None:
    bootstrap_builder = import_module("app.modules.module2.bootstrap.support_builder")
    service_builder = import_module("app.modules.module2.services.extraction.support_builder")

    assert (
        bootstrap_builder.build_module2_main_support_bundle
        is service_builder.build_module2_main_support_bundle
    )
    assert (
        bootstrap_builder.build_module2_bootstrap_runtime_bundle
        is service_builder.build_module2_bootstrap_runtime_bundle
    )
