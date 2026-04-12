from __future__ import annotations

from .endpoints.extraction_assistant import build_router as build_extraction_assistant_router
from .endpoints.extraction_request import build_router as build_extraction_request_router
from .endpoints.extraction_support import build_router as build_extraction_support_router
from .endpoints.sync import build_router as build_sync_router


def build_module2_api_routers(
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
    return (
        build_extraction_request_router(
            extraction_request_runtime=extraction_request_runtime,
        ),
        build_extraction_support_router(
            office_preview_request_runtime=office_preview_request_runtime,
            document_tools_runtime=document_tools_runtime,
            clear_cache_request=clear_cache_request,
            serve_layout_preview=serve_layout_preview,
            serve_artifact=serve_artifact,
            build_health_payload=build_health_payload,
        ),
        build_extraction_assistant_router(
            assistant1_runtime=assistant1_runtime,
        ),
        build_sync_router(
            list_outbox_rows=list_outbox_rows,
            get_outbox_row=get_outbox_row,
            build_list_response=build_list_response,
            serialize_outbox_row=serialize_outbox_row,
            metrics_snapshot=metrics_snapshot,
        ),
    )
