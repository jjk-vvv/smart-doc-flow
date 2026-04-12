from __future__ import annotations

import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.sql.common import (
    READ_STATEMENTS,
    WRITE_STATEMENTS,
    detect_statement_type,
    extract_json_object,
    is_single_statement,
    quote_ident,
)


# ---------------------------------------------------------------------------
# detect_statement_type
# ---------------------------------------------------------------------------

def test_detect_select() -> None:
    assert detect_statement_type("SELECT * FROM t") == "select"


def test_detect_insert() -> None:
    assert detect_statement_type("INSERT INTO t VALUES (1)") == "insert"


def test_detect_update() -> None:
    assert detect_statement_type("UPDATE t SET a=1") == "update"


def test_detect_delete() -> None:
    assert detect_statement_type("DELETE FROM t") == "delete"


def test_detect_create() -> None:
    assert detect_statement_type("CREATE TABLE t (id uuid)") == "create"


def test_detect_alter() -> None:
    assert detect_statement_type("ALTER TABLE t ADD COLUMN x text") == "alter"


def test_detect_drop() -> None:
    assert detect_statement_type("DROP TABLE t") == "drop"


def test_detect_with() -> None:
    assert detect_statement_type("WITH cte AS (SELECT 1) SELECT * FROM cte") == "with"


def test_detect_empty_returns_empty() -> None:
    assert detect_statement_type("") == ""


def test_detect_whitespace_only_returns_empty() -> None:
    assert detect_statement_type("   ") == ""


def test_detect_case_insensitive() -> None:
    assert detect_statement_type("select id from users") == "select"


# ---------------------------------------------------------------------------
# is_single_statement
# ---------------------------------------------------------------------------

def test_single_statement_no_semicolon() -> None:
    assert is_single_statement("SELECT 1") is True


def test_single_statement_trailing_semicolon_ok() -> None:
    assert is_single_statement("SELECT 1;") is True


def test_multiple_statements_returns_false() -> None:
    assert is_single_statement("SELECT 1; SELECT 2") is False


def test_empty_sql_returns_false() -> None:
    assert is_single_statement("") is False


# ---------------------------------------------------------------------------
# quote_ident
# ---------------------------------------------------------------------------

def test_quote_ident_simple() -> None:
    assert quote_ident("my_table") == '"my_table"'


def test_quote_ident_strips_existing_double_quotes() -> None:
    # Internal double quotes are removed (not doubled)
    result = quote_ident('table"name')
    assert result == '"tablename"'


def test_quote_ident_empty_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        quote_ident("")


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------

def test_extract_json_plain_object() -> None:
    result = extract_json_object('{"key": "val"}')
    assert result == {"key": "val"}


def test_extract_json_from_markdown_code_block() -> None:
    text = '```json\n{"sql": "SELECT 1;"}\n```'
    result = extract_json_object(text)
    assert result["sql"] == "SELECT 1;"


def test_extract_json_nested_object() -> None:
    text = '{"a": {"b": 1}}'
    result = extract_json_object(text)
    assert result["a"]["b"] == 1


def test_extract_json_with_surrounding_text() -> None:
    text = 'Here is the result: {"ok": true} end.'
    result = extract_json_object(text)
    assert result["ok"] is True


def test_extract_json_empty_raises() -> None:
    import pytest
    with pytest.raises((ValueError, Exception)):
        extract_json_object("")


def test_extract_json_no_json_raises() -> None:
    import pytest
    with pytest.raises(Exception):
        extract_json_object("no json here at all")


def test_extract_json_array_raises() -> None:
    import pytest
    # Arrays are not JSON objects → should raise
    with pytest.raises((ValueError, Exception)):
        extract_json_object("[1, 2, 3]")


# ---------------------------------------------------------------------------
# WRITE_STATEMENTS and READ_STATEMENTS sets
# ---------------------------------------------------------------------------

def test_write_statements_contains_expected() -> None:
    for stmt in ("insert", "update", "delete", "create", "drop", "alter", "truncate"):
        assert stmt in WRITE_STATEMENTS, f"Expected {stmt!r} in WRITE_STATEMENTS"


def test_read_statements_contains_expected() -> None:
    for stmt in ("select", "with", "show", "explain"):
        assert stmt in READ_STATEMENTS, f"Expected {stmt!r} in READ_STATEMENTS"


def test_write_and_read_are_disjoint() -> None:
    overlap = WRITE_STATEMENTS & READ_STATEMENTS
    assert not overlap, f"Unexpected overlap: {overlap}"
