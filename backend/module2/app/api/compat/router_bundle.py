from __future__ import annotations

import warnings

from ..v1.router_bundle import build_module2_api_routers as _build_module2_api_routers


def build_module2_routers(
    *,
    extraction_request_runtime,
    office_preview_request_runtime,
    document_tools_runtime,
    clear_cache_request,
    serve_layout_preview,
    serve_artifact,
    build_health_payload,
    assistant1_runtime,
    list_outbox_rows,
    get_outbox_row,
    build_list_response,
    serialize_outbox_row,
    metrics_snapshot,
) -> tuple:
    warnings.warn(
        "module2.app.routes.router_bundle is deprecated; "
        "use module2.app.api.v1.router_bundle.build_module2_api_routers instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _build_module2_api_routers(
        extraction_request_runtime=extraction_request_runtime,
        office_preview_request_runtime=office_preview_request_runtime,
        document_tools_runtime=document_tools_runtime,
        clear_cache_request=clear_cache_request,
        serve_layout_preview=serve_layout_preview,
        serve_artifact=serve_artifact,
        build_health_payload=build_health_payload,
        assistant1_runtime=assistant1_runtime,
        list_outbox_rows=list_outbox_rows,
        get_outbox_row=get_outbox_row,
        build_list_response=build_list_response,
        serialize_outbox_row=serialize_outbox_row,
        metrics_snapshot=metrics_snapshot,
    )


__all__ = [
    "build_module2_routers",
]

