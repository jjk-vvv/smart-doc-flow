from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

try:
    from app.assistant_1.api_models import Assistant1ChatStreamRequest
except ModuleNotFoundError:  # pragma: no cover - direct file-loading tests can fall back to plain dict
    Assistant1ChatStreamRequest = dict


def build_router(*, assistant1_runtime) -> APIRouter:
    router = APIRouter(prefix="/extract", tags=["extraction"])

    def _resolve_expected_tenant_id(request: Request) -> str:
        headers = request.headers if request is not None else {}
        return str(
            headers.get("x-authenticated-tenant-id")
            or headers.get("x-authenticated-user-id")
            or headers.get("x-tenant-id")
            or ""
        ).strip()

    @router.get("/assistant1/sessions/{session_id}")
    async def extract_assistant1_session(
        session_id: str,
        request: Request,
        limit: int = Query(default=40, ge=1, le=200),
    ) -> JSONResponse:
        persistence = getattr(assistant1_runtime, "persistence", None)
        if persistence is None:
            raise HTTPException(status_code=503, detail="assistant session persistence unavailable")

        expected_tenant_id = _resolve_expected_tenant_id(request)
        session = await persistence.fetch_session(session_id, expected_tenant_id=expected_tenant_id)
        messages = await persistence.list_messages(
            session_id,
            limit=limit,
            expected_tenant_id=expected_tenant_id,
        )
        if not isinstance(session, dict) and not messages:
            raise HTTPException(status_code=404, detail="assistant session not found")

        payload = {
            "session_id": str(session_id or "").strip(),
            "summary_used": str((session or {}).get("summary_text") or ""),
            "current_object_lock": (
                (session or {}).get("current_object_lock_json")
                if isinstance((session or {}).get("current_object_lock_json"), dict)
                else None
            ),
            "messages": messages,
            "file_hash": str((session or {}).get("file_hash") or ""),
            "file_name": str((session or {}).get("file_name") or ""),
            "metadata": (
                (session or {}).get("metadata_json")
                if isinstance((session or {}).get("metadata_json"), dict)
                else {}
            ),
        }
        return JSONResponse(payload)

    @router.post("/assistant1/chat/stream")
    async def extract_assistant1_chat_stream(payload: Assistant1ChatStreamRequest) -> StreamingResponse:
        history = []
        if isinstance(payload, dict):
            history = list(payload.get("history") or [])
            message = str(payload.get("message") or "")
            file_hash = str(payload.get("file_hash") or "")
            max_steps = int(payload.get("max_steps") or 6)
            top_k = int(payload.get("top_k") or 8)
            session_id = str(payload.get("session_id") or "")
            debug = bool(payload.get("debug"))
            resume_run_id = str(payload.get("resume_run_id") or "")
            after_seq = max(0, int(payload.get("after_seq") or 0))
            extra_context = payload.get("extra_context") if isinstance(payload.get("extra_context"), dict) else {}
            client_caps = payload.get("client_caps") if isinstance(payload.get("client_caps"), dict) else {}
            supports_replace = bool(client_caps.get("supports_replace"))
        else:
            history = [item.model_dump(mode="json") for item in payload.history]
            message = payload.message
            file_hash = payload.file_hash
            max_steps = payload.max_steps
            top_k = payload.top_k
            session_id = payload.session_id or ""
            debug = payload.debug
            resume_run_id = payload.resume_run_id
            after_seq = payload.after_seq
            extra_context = payload.extra_context if isinstance(payload.extra_context, dict) else {}
            supports_replace = bool(payload.client_caps.supports_replace)

        return StreamingResponse(
            assistant1_runtime.stream_chat(
                user_message=message,
                file_hash=file_hash,
                history=history,
                max_steps=max_steps,
                top_k=top_k,
                session_id=session_id,
                debug=debug,
                resume_run_id=resume_run_id,
                after_seq=after_seq,
                extra_context=extra_context,
                client_supports_replace=supports_replace,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
