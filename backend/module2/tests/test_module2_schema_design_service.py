from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.sql.schema_design import Assistant1SchemaDesignService


def _make_service(provider_output_text: str = "", provider_configured: bool = True) -> Assistant1SchemaDesignService:
    service = Assistant1SchemaDesignService.__new__(Assistant1SchemaDesignService)
    provider = MagicMock()
    provider.configured = provider_configured
    result_mock = MagicMock()
    result_mock.output_text = provider_output_text
    provider.complete.return_value = result_mock
    service.provider = provider
    settings = MagicMock()
    settings.chat_max_output_tokens = 2400
    service.settings = settings
    return service


# ---------------------------------------------------------------------------
# Fallback schema design (provider returns invalid JSON)
# ---------------------------------------------------------------------------

def test_fallback_triggered_on_invalid_json() -> None:
    service = _make_service(provider_output_text="this is not json")
    result = service.design_schema_draft(objective="设计一张存储年度指标的表")
    assert result.get("ok") is True
    assert isinstance(result.get("tables"), list)
    assert len(result["tables"]) >= 1


def test_fallback_schema_has_id_primary_key() -> None:
    service = _make_service(provider_output_text="invalid json")
    result = service.design_schema_draft(objective="设计一张表")
    table = result["tables"][0]
    col_names = [c["name"] for c in table["columns"]]
    assert "id" in col_names
    assert table["primary_key"] == ["id"]


def test_fallback_schema_has_audit_columns() -> None:
    service = _make_service(provider_output_text="invalid json")
    result = service.design_schema_draft(objective="设计一张表")
    table = result["tables"][0]
    col_names = [c["name"] for c in table["columns"]]
    assert "source_file_hash" in col_names
    assert "created_at" in col_names


def test_fallback_ddl_is_nonempty() -> None:
    service = _make_service(provider_output_text="bad json")
    result = service.design_schema_draft(objective="设计一张表")
    assert isinstance(result.get("ddl_statements"), list)
    assert len(result["ddl_statements"]) >= 1
    ddl_text = " ".join(result["ddl_statements"])
    assert "CREATE TABLE" in ddl_text.upper()


# ---------------------------------------------------------------------------
# Fallback heuristic column detection from objective text
# ---------------------------------------------------------------------------

def test_fallback_year_keyword_adds_stat_year_column() -> None:
    service = _make_service(provider_output_text="bad json")
    result = service.design_schema_draft(objective="存储按年度统计的环境数据")
    table = result["tables"][0]
    col_names = [c["name"] for c in table["columns"]]
    assert "stat_year" in col_names


def test_fallback_metric_keyword_adds_indicator_name_column() -> None:
    service = _make_service(provider_output_text="bad json")
    result = service.design_schema_draft(objective="记录各种指标的采集值")
    table = result["tables"][0]
    col_names = [c["name"] for c in table["columns"]]
    assert "indicator_name" in col_names


def test_fallback_value_keyword_adds_indicator_value_column() -> None:
    service = _make_service(provider_output_text="bad json")
    result = service.design_schema_draft(objective="存储数值和单位")
    table = result["tables"][0]
    col_names = [c["name"] for c in table["columns"]]
    assert "indicator_value" in col_names


# ---------------------------------------------------------------------------
# file_context appears in prompt (verified via provider.complete call args)
# ---------------------------------------------------------------------------

def test_file_context_passed_to_provider_prompt() -> None:
    service = _make_service(provider_output_text="bad json")
    service.design_schema_draft(
        objective="设计一张表",
        file_context="这份文档包含2021年民政数据，字段包括机构数量、床位数等。",
    )
    call_args = service.provider.complete.call_args
    messages = call_args.kwargs.get("messages") or call_args.args[0]
    combined = " ".join(str(m) for m in messages)
    assert "民政数据" in combined


# ---------------------------------------------------------------------------
# Provider returns valid JSON — normal parse path
# ---------------------------------------------------------------------------

def test_valid_json_from_provider_parsed_correctly() -> None:
    valid_output = '''{
        "design_summary": "一张统计指标表",
        "tables": [{
            "name": "stat_records",
            "purpose": "存储统计指标",
            "columns": [
                {"name": "id", "type": "uuid", "nullable": false, "description": "主键"},
                {"name": "value", "type": "numeric", "nullable": true, "description": "数值"}
            ],
            "primary_key": ["id"],
            "unique_constraints": [],
            "indexes": []
        }],
        "assumptions": ["使用UUID作为主键"]
    }'''
    service = _make_service(provider_output_text=valid_output)
    result = service.design_schema_draft(objective="设计统计指标表")
    assert result.get("ok") is True
    assert result["tables"][0]["name"] == "stat_records"
    assert result["design_summary"] == "一张统计指标表"


# ---------------------------------------------------------------------------
# Provider not configured
# ---------------------------------------------------------------------------

def test_provider_not_configured_returns_error() -> None:
    service = _make_service(provider_configured=False)
    result = service.design_schema_draft(objective="设计一张表")
    assert result.get("ok") is False
    assert "not configured" in str(result.get("error", "")).lower()


# ---------------------------------------------------------------------------
# Empty objective returns error
# ---------------------------------------------------------------------------

def test_empty_objective_returns_error() -> None:
    service = _make_service()
    result = service.design_schema_draft(objective="")
    assert result.get("ok") is False
