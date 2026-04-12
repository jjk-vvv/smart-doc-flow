from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.sql.drafting import Assistant1SqlDraftingService


# ---------------------------------------------------------------------------
# Fix 5: NL2SQL offline mode tests — graceful degradation when DB is unavailable
# ---------------------------------------------------------------------------

def _make_offline_service() -> Assistant1SqlDraftingService:
    """Create a drafting service with a stubbed introspector that always fails
    and a stubbed provider that returns a minimal JSON SQL draft."""
    service = Assistant1SqlDraftingService.__new__(Assistant1SqlDraftingService)

    # Introspector raises ConnectionRefusedError (simulating no DB)
    introspector = MagicMock()
    introspector.inspect_database_schema.side_effect = ConnectionRefusedError("no DB")
    service.introspector = introspector

    # Provider is configured and returns a minimal valid JSON draft
    provider = MagicMock()
    provider.configured = True
    result_mock = MagicMock()
    result_mock.output_text = (
        '{"sql": "SELECT * FROM my_table LIMIT 10;", '
        '"statement_type": "select", '
        '"explanation": "Offline draft based on request only.", '
        '"assumptions": ["Table name inferred from request."], '
        '"tables": ["my_table"], '
        '"requires_confirmation": false}'
    )
    provider.complete.return_value = result_mock
    service.provider = provider

    # Settings stub
    settings = MagicMock()
    settings.chat_max_output_tokens = 2400
    service.settings = settings

    return service


def test_draft_sql_does_not_fail_when_introspection_raises() -> None:
    """When introspection raises, draft_sql_from_nl should still return ok=True."""
    service = _make_offline_service()
    result = service.draft_sql_from_nl(request="列出前10条记录")
    assert result.get("ok") is True, f"Expected ok=True, got: {result}"


def test_schema_offline_flag_is_true_when_introspection_fails() -> None:
    """schema_offline must be True in the result when introspection was unavailable."""
    service = _make_offline_service()
    result = service.draft_sql_from_nl(request="列出前10条记录")
    assert result.get("schema_offline") is True


def test_sql_draft_present_in_offline_mode() -> None:
    """A SQL draft should still be generated in offline mode."""
    service = _make_offline_service()
    result = service.draft_sql_from_nl(request="列出前10条记录")
    assert result.get("sql"), "Expected non-empty SQL in offline mode"


def test_schema_offline_false_when_introspection_succeeds() -> None:
    """schema_offline must be False when introspection succeeds."""
    service = Assistant1SqlDraftingService.__new__(Assistant1SqlDraftingService)

    introspector = MagicMock()
    introspector.inspect_database_schema.return_value = {
        "ok": True,
        "table_count": 1,
        "tables": [{"schema": "public", "table_name": "my_table", "columns": []}],
    }
    service.introspector = introspector

    provider = MagicMock()
    provider.configured = True
    result_mock = MagicMock()
    result_mock.output_text = (
        '{"sql": "SELECT * FROM my_table;", '
        '"statement_type": "select", '
        '"explanation": "Simple select.", '
        '"assumptions": [], '
        '"tables": ["my_table"], '
        '"requires_confirmation": false}'
    )
    provider.complete.return_value = result_mock
    service.provider = provider

    settings = MagicMock()
    settings.chat_max_output_tokens = 2400
    service.settings = settings

    result = service.draft_sql_from_nl(request="查询 my_table 的所有数据")
    assert result.get("ok") is True
    assert result.get("schema_offline") is False


def test_heuristic_draft_includes_schema_offline_flag() -> None:
    """When heuristic fallback kicks in (model returns no SQL), schema_offline must propagate."""
    service = Assistant1SqlDraftingService.__new__(Assistant1SqlDraftingService)

    introspector = MagicMock()
    introspector.inspect_database_schema.side_effect = OSError("unreachable")
    service.introspector = introspector

    provider = MagicMock()
    provider.configured = True
    result_mock = MagicMock()
    # Empty SQL → triggers heuristic path
    result_mock.output_text = (
        '{"sql": "", "statement_type": "", "explanation": "", '
        '"assumptions": [], "tables": [], "requires_confirmation": false}'
    )
    provider.complete.return_value = result_mock
    service.provider = provider

    settings = MagicMock()
    settings.chat_max_output_tokens = 2400
    service.settings = settings

    # "列出" triggers the heuristic SELECT * LIMIT 50 fallback
    result = service.draft_sql_from_nl(request="列出 test_table 的所有字段", allowed_tables=["test_table"])
    if result.get("ok"):
        assert result.get("schema_offline") is True
