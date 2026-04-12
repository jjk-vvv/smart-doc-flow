from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_llm_bundle_module = import_module("module2.app.bootstrap.schema_llm")


def _sanitize_field_name(value: object) -> str:
    return "_".join(str(value or "").strip().lower().replace("/", " ").split())


def _coerce_field_type(value: object) -> str:
    text = str(value or "string").strip().lower()
    return text if text in {"string", "number", "integer", "date", "boolean"} else "string"


def _upsert_schema_field_candidate(out: dict[str, str], field_name: object, field_type: object, skip_low_value: bool) -> None:
    key = _sanitize_field_name(field_name)
    if not key:
        return
    if skip_low_value and key in {"name", "page"}:
        return
    out[key] = _coerce_field_type(field_type)


def _filter_auto_schema_fields(fields: dict[str, str], max_fields: int) -> dict[str, str]:
    return dict(list(fields.items())[:max_fields])


class _FakeProviderGraph:
    def __init__(self, payload: dict[str, object]) -> None:
        self._provider = object()
        self.llm = None
        self._payload = payload
        self.messages = None

    async def invoke_json_object(self, messages, max_tokens: int, purpose: str):
        self.messages = messages
        self.max_tokens = max_tokens
        self.purpose = purpose
        return self._payload


class _FakeLlm:
    def __init__(self, content) -> None:
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return SimpleNamespace(content=self.content)


def _build_bundle(graph) -> object:
    return main_schema_llm_bundle_module.build_module2_main_schema_llm_bundle(
        graph=graph,
        getenv=lambda key, default="": default,
        extract_text_for_schema=lambda markdown, table_blocks, figure_blocks, max_chars: str(markdown or "").strip()[:max_chars],
        upsert_schema_field_candidate=_upsert_schema_field_candidate,
        filter_auto_schema_fields=_filter_auto_schema_fields,
    )


def test_build_module2_main_schema_llm_bundle_extracts_json_payload() -> None:
    bundle = _build_bundle(graph=SimpleNamespace(_provider=None, llm=None))

    payload = bundle.extract_json_payload(
        """
        ```json
        {"fields": [{"field_name": "Report Date", "field_type": "date"}]}
        ```
        """
    )

    assert payload == {"fields": [{"field_name": "Report Date", "field_type": "date"}]}


def test_module2_main_schema_llm_bundle_infers_fields_via_provider_json_path() -> None:
    graph = _FakeProviderGraph(
        {
            "fields": [
                {"field_name": "Invoice Total", "field_type": "number"},
                {"field_name": "Name", "field_type": "string"},
            ]
        }
    )
    bundle = _build_bundle(graph=graph)

    out = asyncio.run(
        bundle.infer_schema_fields_llm(
            "invoice.pdf",
            "Invoice Total: 1200",
            [],
            None,
            4,
        )
    )

    assert out == {"invoice_total": "number"}
    assert graph.purpose == "schema_planner"
    assert graph.messages[0]["role"] == "system"


def test_module2_main_schema_llm_bundle_infers_fields_via_llm_text_fallback() -> None:
    llm = _FakeLlm(
        [
            {
                "text": """
                ```json
                {"fields": [{"field_name": "Report Date", "field_type": "date"}, {"field_name": "Item Count", "field_type": "integer"}]}
                ```
                """
            }
        ]
    )
    graph = SimpleNamespace(_provider=None, llm=llm)
    bundle = _build_bundle(graph=graph)

    out = asyncio.run(
        bundle.infer_schema_fields_llm(
            "report.docx",
            "Report Date: 2026-03-01\nItem Count: 4",
            [],
            None,
            4,
        )
    )

    assert out == {
        "report_date": "date",
        "item_count": "integer",
    }
    assert llm.messages[1]["role"] == "user"
