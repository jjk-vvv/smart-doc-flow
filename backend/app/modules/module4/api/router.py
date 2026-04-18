from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.auth_deps import AuthenticatedUser
from app.core.auth_security import normalize_str
from app.services.auth_service import get_auth_service

from .endpoints.gateway import router as gateway_router
from .deps import Module4RouterDeps
from .v1.router import build_api_v1_router
from ..core.application import (
    _schedule_rebuild_job,
    _submit_ingest_job,
    module4_app_runtime,
)
from ..core.runtime import module4_internal_token_mode


def _merge_authenticated_headers(request: Request, headers: dict[str, str]) -> None:
    scope_headers = list(request.scope.get("headers") or [])
    existing_keys = {bytes(key).lower() for key, _ in scope_headers}
    for raw_key, raw_value in headers.items():
        key = normalize_str(raw_key)
        value = normalize_str(raw_value)
        if not key or not value:
            continue
        key_bytes = key.lower().encode("latin-1")
        if key_bytes in existing_keys:
            continue
        scope_headers.append((key_bytes, value.encode("utf-8")))
        existing_keys.add(key_bytes)
    request.scope["headers"] = scope_headers


async def _resolve_module4_access(
    request: Request,
    auth_service=Depends(get_auth_service),
) -> AuthenticatedUser | None:
    internal_token = normalize_str(request.headers.get("x-module4-internal-token"))
    if module4_internal_token_mode() == "required" and internal_token:
        module4_app_runtime.validate_internal_request(request)
        return None

    authenticated = await auth_service.authenticate_request(request)
    current_user = AuthenticatedUser(
        user_id=normalize_str(authenticated.get("id")),
        name=normalize_str(authenticated.get("name")),
        email=normalize_str(authenticated.get("email")),
        phone=normalize_str(authenticated.get("phone")),
        status=normalize_str(authenticated.get("status")) or "active",
        session_id=normalize_str(authenticated.get("session_id")),
    )
    request.state.authenticated_user = current_user
    _merge_authenticated_headers(request, current_user.to_forward_headers())
    return current_user


def _build_local_module4_router() -> APIRouter:
    deps = Module4RouterDeps(
        storage_getter=module4_app_runtime.storage_getter,
        query_helpers=module4_app_runtime.query_helpers,
        insight_helpers=module4_app_runtime.insight_helpers,
        workspace_builder_getter=module4_app_runtime.workspace_builder_getter,
        neo4j_graph_projector_getter=module4_app_runtime.neo4j_graph_projector_getter,
        graphrag_indexer_getter=module4_app_runtime.graphrag_indexer_getter,
        tenant_from_request=module4_app_runtime.tenant_from_request,
        validate_internal_request=lambda _request: None,
        parse_csv_list=module4_app_runtime.parse_csv_list,
        submit_ingest_job=_submit_ingest_job,
        schedule_rebuild_job=_schedule_rebuild_job,
        now_utc=module4_app_runtime.now_utc,
    )
    return build_api_v1_router(deps=deps)


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(gateway_router)
    router.include_router(
        _build_local_module4_router(),
        dependencies=[Depends(_resolve_module4_access)],
    )
    return router


router = build_router()

__all__ = ["build_router", "router"]
