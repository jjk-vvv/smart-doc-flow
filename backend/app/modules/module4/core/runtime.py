from __future__ import annotations

"""Canonical composition runtime entrypoints for Module4 app assembly."""

from . import app_runtime as _service_module


Module4CompositionComponents = _service_module.Module4BootstrapComponents
Module4BootstrapComponents = _service_module.Module4BootstrapComponents
Module4AppRuntime = _service_module.Module4AppRuntime

load_module4_env = _service_module.load_module4_env
cors_origins = _service_module.cors_origins
default_tenant = _service_module.default_tenant
tenant_from_request = _service_module.tenant_from_request
now_utc = _service_module.now_utc
parse_csv_list = _service_module.parse_csv_list
build_insight_runtime_helpers = _service_module.build_insight_runtime_helpers
build_default_composition_components = _service_module.build_default_composition_components
build_default_bootstrap_components = _service_module.build_default_bootstrap_components


__all__ = [
    "Module4CompositionComponents",
    "Module4BootstrapComponents",
    "Module4AppRuntime",
    "load_module4_env",
    "cors_origins",
    "default_tenant",
    "tenant_from_request",
    "now_utc",
    "parse_csv_list",
    "build_insight_runtime_helpers",
    "build_default_composition_components",
    "build_default_bootstrap_components",
]
