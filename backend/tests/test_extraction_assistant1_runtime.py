from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.modules.extraction.assistant1_runtime import (
    ExtractionAssistant1Provider,
    NativeAssistant1Runtime,
)
from app.modules.extraction.config import ExtractionSettings


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


def _extraction_settings() -> ExtractionSettings:
    return ExtractionSettings(
        module2_port_hint="",
        artifact_root_dir="",
        module2_execution_mode="auto",
        module2_fallback_to_upstream=True,
        module2_worker_timeout_sec=900.0,
        module2_worker_python="",
        module2_sidecar_mode="auto",
        module2_sidecar_python="",
        module2_sidecar_startup_timeout_sec=120.0,
        max_file_mb=25,
        doc_to_pdf_enable=True,
        office_preview_timeout_sec=120.0,
        office_preview_job_ttl_sec=1800.0,
        office_preview_job_cap=240,
        extract_job_ttl_sec=7200.0,
        extract_job_cap=240,
        shadow_poll_timeout_sec=2700.0,
        shadow_poll_interval_sec=1.2,
        assistant1_mode="native",
        assistant1_fallback_to_legacy=True,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


class StubProvider(ExtractionAssistant1Provider):
    def __init__(self, chunks: list[str], *, configured: bool = True) -> None:
        self.settings = type(
            "StubSettings",
            (),
            {
                "chat_max_output_tokens": 2400,
                "chat_reasoning_effort": "minimal",
                "chat_text_verbosity": "medium",
            },
        )()
        self._chunks = list(chunks)
        self._configured = configured

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def model(self) -> str:
        return "gpt-5-mini"

    @property
    def base_url(self) -> str:
        return "https://example.test"

    @property
    def endpoint_path(self) -> str:
        return "/v1/responses"

    def stream_text(self, *, messages, instructions):
        del messages, instructions
        for chunk in self._chunks:
            yield chunk

    def complete_text(
        self,
        *,
        messages,
        instructions,
        max_output_tokens=None,
        reasoning_effort=None,
        text_verbosity=None,
    ) -> str:
        del messages, instructions, max_output_tokens, reasoning_effort, text_verbosity
        return "".join(self._chunks)


def _write_context_files(settings: Settings, file_hash: str) -> None:
    shadow_root = settings.data_root_dir / "module2" / "runlogs" / "unified_extraction_shadow_jobs"
    shadow_root.mkdir(parents=True, exist_ok=True)
    shadow_payload = {
        "payload": {
            "job_id": "extract_job_demo_2",
            "status": "completed",
            "updated_at": 456.0,
            "documents": [
                {
                    "file_name": "demo.pdf",
                    "file_hash": file_hash,
                    "track": "VisualTrack",
                    "result": {
                        "contract_amount": {
                            "value": "1000000 CNY",
                            "confidence": 0.93,
                            "source_ref_id": "ref-2",
                        }
                    },
                    "trace_hits": [
                        {
                            "file_name": "demo.pdf",
                            "file_hash": file_hash,
                            "object_type": "field",
                            "object_id": "contract_amount",
                            "ref_id": "ref-2",
                            "page": 1,
                            "snippet": "Contract amount is 1000000 CNY",
                        }
                    ],
                }
            ],
        }
    }
    (shadow_root / "extract_job_demo_2.json").write_text(
        json.dumps(shadow_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    artifact_dir = settings.data_root_dir / "module2" / "artifacts" / "assistant_1_source" / file_hash[:12]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    markdown_rel = f"assistant_1_source/{file_hash[:12]}/demo_source.md"
    markdown_path = settings.data_root_dir / "module2" / "artifacts" / markdown_rel
    markdown_path.write_text(
        '<ref id="ref-2">Contract amount is 1000000 CNY.</ref>',
        encoding="utf-8",
    )
    (artifact_dir / "demo_source_meta_123.json").write_text(
        json.dumps(
            {
                "file_name": "demo.pdf",
                "file_hash": file_hash,
                "track": "VisualTrack",
                "markdown_artifact_path": markdown_rel.replace("\\", "/"),
                "markdown_artifact_url": "/extract/artifact/" + markdown_rel.replace("\\", "/"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_native_runtime_stream_emits_compatible_sse_sequence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    extraction_settings = _extraction_settings()
    file_hash = "feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface"
    _write_context_files(settings, file_hash)
    runtime = NativeAssistant1Runtime(
        extraction_settings=extraction_settings,
        provider=StubProvider(["part1", "part2"]),
    )

    async def collect() -> list[str]:
        chunks = []
        async for chunk in runtime.stream_chat(
            settings=settings,
            user_message="\u8bf7\u603b\u7ed3\u8fd9\u4efd\u6587\u6863",
            file_hash=file_hash,
            history=[],
            top_k=5,
            session_id="sess-1",
            client_supports_replace=True,
        ):
            chunks.append(chunk.decode("utf-8"))
        return chunks

    payload = "".join(asyncio.run(collect()))

    assert "event: stream.open" in payload
    assert "event: assistant.start" in payload
    assert "event: evidence.bundle" in payload
    assert "event: status" in payload
    assert "event: assistant.delta" in payload
    assert "event: assistant.done" in payload


def test_native_runtime_health_reports_not_ready_when_provider_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = NativeAssistant1Runtime(
        extraction_settings=_extraction_settings(),
        provider=StubProvider([], configured=False),
    )

    payload = runtime.health_payload(settings)

    assert payload["ok"] is False
    assert payload["configured"] is False
    assert payload["runtime_ready"] is False


def test_native_runtime_request_readiness_requires_context_for_bound_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = NativeAssistant1Runtime(
        extraction_settings=_extraction_settings(),
        provider=StubProvider(["ok"], configured=True),
    )

    payload = runtime.request_readiness_payload(
        settings,
        file_hash="missing-context-hash",
    )

    assert payload["runtime_ready"] is True
    assert payload["context_required"] is True
    assert payload["context_found"] is False
    assert payload["fallback_recommended"] is True


def test_native_runtime_builds_direct_numeric_answer_from_frontend_snapshot() -> None:
    answer = NativeAssistant1Runtime._build_frontend_snapshot_answer(
        user_message="\u5f53\u524d\u6587\u6863\u7684\u7edf\u8ba1\u5e74\u4efd\u662f\u591a\u5c11\uff1f\u53ea\u56de\u7b54\u6570\u5b57\u3002",
        extra_context={
            "current_document": {
                "file_name": "stats_2021.docx",
                "top_fields": [
                    {"label": "\u7edf\u8ba1\u5e74\u4efd", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "\u57fa\u91d1\u4f1a\u603b\u6570", "value": "8877", "confidence": 98, "page": 12},
                ],
            }
        },
    )

    assert answer == "2021"


def test_native_runtime_replaces_placeholder_answer_with_frontend_snapshot_summary() -> None:
    answer = NativeAssistant1Runtime._ground_answer_with_frontend_context(
        user_message=(
            "\u8bf7\u7528\u4e2d\u6587\u6982\u62ec\u5f53\u524d\u9009\u4e2d\u6587\u6863\u7684\u6838\u5fc3\u5185\u5bb9\uff0c"
            "\u5e76\u5217\u51fa\u4f60\u5f53\u524d\u6700\u786e\u5b9a\u76843\u4e2a\u5b57\u6bb5\u3002"
        ),
        answer="\u5b57\u6bb5\u540d\uff1a\u6587\u6863\u6807\u9898 / \u4e3b\u65e8\n\u5f53\u524d\u503c:[placeholder]",
        extra_context={
            "current_document": {
                "file_name": "stats_2021.docx",
                "summary": (
                    "\u8be5\u6587\u6863\u6982\u8ff0\u4e862021\u5e74\u7684\u76f8\u5173\u7edf\u8ba1\u60c5\u51b5\uff0c"
                    "\u5e76\u7ed9\u51fa\u673a\u6784\u8bbe\u65bd\u3001\u8001\u5e74\u4eba\u53e3\u548c\u57fa\u91d1\u4f1a\u7b49\u6570\u636e\u3002"
                ),
                "top_fields": [
                    {"label": "\u7edf\u8ba1\u5e74\u4efd", "value": "2021", "confidence": 98, "page": 1},
                    {"label": "\u57fa\u91d1\u4f1a\u603b\u6570", "value": "8877", "confidence": 98, "page": 12},
                    {"label": "\u670d\u52a1\u5e8a\u4f4d\u603b\u6570", "value": "530.5", "confidence": 99, "page": 4},
                ],
            }
        },
    )

    assert "\u5f53\u524d\u9009\u4e2d\u6587\u6863\u7684\u6838\u5fc3\u5185\u5bb9" in answer
    assert "\u7edf\u8ba1\u5e74\u4efd" in answer
    assert "\u57fa\u91d1\u4f1a\u603b\u6570" in answer
    assert "placeholder" not in answer


def test_native_runtime_short_circuits_broad_document_summary_requests_with_context() -> None:
    question = (
        "\u8bf7\u7528\u4e2d\u6587\u6982\u62ec\u5f53\u524d\u9009\u4e2d\u6587\u6863\u7684\u6838\u5fc3\u5185\u5bb9\uff0c"
        "\u5e76\u5217\u51fa\u4f60\u5f53\u524d\u6700\u786e\u5b9a\u76843\u4e2a\u5b57\u6bb5\u3002"
    )
    assert NativeAssistant1Runtime._should_short_circuit_with_frontend_snapshot(
        user_message=question,
        snapshot_answer="\u5f53\u524d\u9009\u4e2d\u6587\u6863\u7684\u6838\u5fc3\u5185\u5bb9\uff1a...",
        extra_context={
            "current_document": {
                "summary": "\u6587\u6863\u5df2\u5b8c\u6210\u89e3\u6790",
                "top_fields": [
                    {"label": "\u7edf\u8ba1\u5e74\u4efd", "value": "2021"},
                    {"label": "\u57fa\u91d1\u4f1a\u603b\u6570", "value": "8877"},
                    {"label": "\u670d\u52a1\u5e8a\u4f4d\u603b\u6570", "value": "530.5"},
                ],
            }
        },
    ) is True


def test_native_runtime_builds_multi_field_snapshot_answer_for_compound_question() -> None:
    answer = NativeAssistant1Runtime._build_frontend_snapshot_answer(
        user_message=(
            "\u8bf7\u57fa\u4e8e\u5f53\u524d\u8868\u683c\uff0c\u6307\u51fa\u5f53\u524d\u8fd9\u6761\u6837\u4f8b\u8bb0\u5f55"
            "\u7684\u8ba2\u5355\u72b6\u6001\u548c\u9500\u552e\u90e8\u95e8\u3002"
        ),
        extra_context={
            "current_document": {
                "file_name": "sales.xlsx",
                "summary": "\u8fd9\u662f\u4e00\u4efd\u9500\u552e\u8ba2\u5355\u6837\u4f8b\u8868\u3002",
                "top_fields": [
                    {"label": "\u7528\u6237\u7f16\u53f7", "value": "US377677", "confidence": 99},
                    {"label": "\u8ba2\u5355\u7f16\u53f7", "value": "P1696644", "confidence": 99},
                    {"label": "\u8ba2\u5355\u65e5\u671f", "value": "2023-09-08", "confidence": 99},
                    {"label": "\u9500\u552e\u90e8\u95e8", "value": "\u9500\u552e\u4e09\u90e8", "confidence": 99},
                    {"label": "\u8ba2\u5355\u72b6\u6001", "value": "\u5df2\u4ed8\u6b3e", "confidence": 95},
                ],
            }
        },
    )

    assert "\u8ba2\u5355\u72b6\u6001" in answer
    assert "\u9500\u552e\u90e8\u95e8" in answer
    assert "\u5df2\u4ed8\u6b3e" in answer
    assert "\u9500\u552e\u4e09\u90e8" in answer


def test_native_runtime_conditional_lookup_without_row_evidence_does_not_guess() -> None:
    question = (
        "\u7ad9\u70b9\u540d\u79f0\u4e3a\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66"
        "\u7684\u8bbe\u5907\u6570\u91cf\u662f\u591a\u5c11\uff1f"
        "\u8bf7\u7ed9\u9875\u7801\u3001\u884c\u53f7\u548cref_id\u3002"
    )
    answer = NativeAssistant1Runtime._build_frontend_snapshot_answer(
        user_message=question,
        extra_context={
            "current_document": {
                "file_name": "air_station.xlsx",
                "top_fields": [
                    {"label": "\u7ad9\u70b9\u540d\u79f0", "value": "\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66", "confidence": 98, "page": 1},
                    {"label": "\u8bbe\u5907\u6570\u91cf", "value": "42", "confidence": 92, "page": 1},
                ],
            }
        },
    )

    assert "\u884c\u7ea7\u8868\u683c\u8bc1\u636e" in answer
    assert "\u65e0\u6cd5\u786e\u8ba4" in answer


def test_native_runtime_conditional_lookup_with_row_evidence_returns_value_and_provenance() -> None:
    question = (
        "\u7ad9\u70b9\u540d\u79f0\u4e3a\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66"
        "\u7684\u8bbe\u5907\u6570\u91cf\u662f\u591a\u5c11\uff1f"
        "\u8bf7\u7ed9\u9875\u7801\u3001\u884c\u53f7\u548cref_id\u3002"
    )
    answer = NativeAssistant1Runtime._build_frontend_snapshot_answer(
        user_message=question,
        extra_context={
            "current_document": {
                "file_name": "air_station.xlsx",
                "table_row_samples": [
                    {
                        "table_id": "tbl_001",
                        "ref_id": "ref_table_001",
                        "page": 3,
                        "headers": ["\u7ad9\u70b9\u540d\u79f0", "\u8bbe\u5907\u6570\u91cf", "\u72b6\u6001"],
                        "rows": [
                            {"row_index": 5, "cells": ["\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66", "42", "\u6b63\u5e38"]},
                        ],
                    }
                ],
                "top_fields": [
                    {"label": "\u7ad9\u70b9\u540d\u79f0", "value": "\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66", "confidence": 98, "page": 1},
                    {"label": "\u8bbe\u5907\u6570\u91cf", "value": "42", "confidence": 92, "page": 1},
                ],
            }
        },
    )

    assert "\u8bbe\u5907\u6570\u91cf=42" in answer
    assert "page=3" in answer
    assert "row_index=5" in answer
    assert "ref_id=ref_table_001" in answer


def test_native_runtime_short_circuit_gate_for_conditional_lookup_requires_provenance_snapshot() -> None:
    question = (
        "\u7ad9\u70b9\u540d\u79f0\u4e3a\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66"
        "\u7684\u8bbe\u5907\u6570\u91cf\u662f\u591a\u5c11\uff1f"
        "\u8bf7\u7ed9\u9875\u7801\u3001\u884c\u53f7\u548cref_id\u3002"
    )
    assert (
        NativeAssistant1Runtime._should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer="\u7ad9\u70b9\u540d\u79f0\u662f\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66\u3002",
            extra_context={},
        )
        is False
    )

    assert (
        NativeAssistant1Runtime._should_short_circuit_with_frontend_snapshot(
            user_message=question,
            snapshot_answer=(
                "\u8bbe\u5907\u6570\u91cf=42\u3002\u8bc1\u636e\uff1a"
                "page=3, row_index=5, ref_id=ref_table_001\u3002"
            ),
            extra_context={},
        )
        is True
    )


def test_native_runtime_conditional_lookup_with_table_prefix_still_requests_row_evidence() -> None:
    question = (
        "\u8bf7\u76f4\u63a5\u67e5\u770b xlsx_t1 \u8868\u683c\uff0c"
        "\u7ad9\u70b9\u540d\u79f0\u4e3a\u6ee8\u5dde\u65b0\u4e8c\u4e2d\u7684 PM10 \u76d1\u6d4b\u503c\u662f\u591a\u5c11\uff1f"
        "\u8bf7\u5199\u660e\u8868\u683c\u3001\u9875\u7801\u3001\u8868\u5185\u884c\u53f7\u3001\u539f\u59cb\u884c\u53f7\u548c ref_id\u3002"
    )
    answer = NativeAssistant1Runtime._build_frontend_snapshot_answer(
        user_message=question,
        extra_context={
            "current_document": {
                "file_name": "air_station.xlsx",
                "top_fields": [
                    {"label": "\u7ad9\u70b9\u540d\u79f0", "value": "\u6ed5\u5dde\u5317\u8f9b\u4e2d\u5b66", "confidence": 98, "page": 1},
                    {"label": "PM10 \u76d1\u6d4b\u503c", "value": "34", "confidence": 92, "page": 1},
                ],
            }
        },
    )

    assert "\u884c\u7ea7\u8868\u683c\u8bc1\u636e" in answer
    assert "\u65e0\u6cd5\u786e\u8ba4" in answer
