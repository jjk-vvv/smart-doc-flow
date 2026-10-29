from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.module4.services.ingestion.runtime import _store_document_alerts


class _FakeStorage:
    def __init__(self, rules: list[dict], fail_insert: bool = False) -> None:
        self.rules = rules
        self.fail_insert = fail_insert
        self.alerts: list[dict[str, Any]] = []

    async def list_rules(self, *, tenant_id: str = "", enabled_only: bool = False) -> list[dict]:
        return list(self.rules)

    async def insert_alert(self, **kwargs: Any) -> dict:
        if self.fail_insert:
            raise RuntimeError("insert failed")
        self.alerts.append(kwargs)
        return {"alert_id": f"alert-{len(self.alerts)}"}


def _rule(rule_id: str, expr: dict, *, severity: str = "yellow") -> dict:
    return {
        "rule_id": rule_id,
        "name": rule_id,
        "severity": severity,
        "rule_kind": "deterministic",
        "enabled": True,
        "expr": expr,
    }


def test_field_rule_generates_one_alert_per_low_confidence_field() -> None:
    storage = _FakeStorage(
        [
            _rule(
                "RULE_LOW_CONFIDENCE",
                {
                    "scope": "field",
                    "path": "confidence",
                    "op": "lt",
                    "value": 0.8,
                    "risk_formula": "1_minus_confidence",
                    "title": "Field confidence too low: {field_name}",
                    "summary": "{file_name} field {field_name} confidence={confidence}",
                },
            )
        ]
    )
    document = {
        "file_name": "report.txt",
        "file_hash": "hash-1",
        "result": {
            "low_field": {"value": "a", "confidence": 0.4},
            "high_field": {"value": "b", "confidence": 0.95},
        },
        "errors": [],
        "soft_warnings": [],
    }

    count = asyncio.run(
        _store_document_alerts(
            storage=storage,
            tenant_id="t1",
            graph_file_id="gf-1",
            doc=document,
            file_name="report.txt",
            file_hash="hash-1",
        )
    )

    assert count == 1
    assert storage.alerts[0]["rule_id"] == "RULE_LOW_CONFIDENCE"
    assert storage.alerts[0]["payload"]["field_name"] == "low_field"
    assert storage.alerts[0]["risk_score"] == pytest.approx(60.0)


def test_document_rule_generates_alert_for_errors() -> None:
    storage = _FakeStorage(
        [
            _rule(
                "RULE_DOC_ERRORS",
                {
                    "scope": "document",
                    "path": "errors",
                    "op": "non_empty",
                    "risk_score": 92.0,
                    "title": "Document parsing errors: {file_name}",
                    "summary": "{file_name} has {errors_count} parsing errors",
                },
                severity="orange",
            )
        ]
    )
    document = {
        "file_name": "broken.pdf",
        "file_hash": "hash-2",
        "result": {},
        "errors": ["parse error"],
        "soft_warnings": [],
    }

    count = asyncio.run(
        _store_document_alerts(
            storage=storage,
            tenant_id="t1",
            graph_file_id=None,
            doc=document,
            file_name="broken.pdf",
            file_hash="hash-2",
        )
    )

    assert count == 1
    assert storage.alerts[0]["severity"] == "orange"
    assert storage.alerts[0]["risk_score"] == pytest.approx(92.0)


def test_rule_storage_failures_never_break_ingestion() -> None:
    class _BrokenStorage:
        async def list_rules(self, **_kwargs: Any) -> list[dict]:
            raise RuntimeError("database down")

        async def insert_alert(self, **_kwargs: Any) -> dict:
            raise RuntimeError("insert down")

    count = asyncio.run(
        _store_document_alerts(
            storage=_BrokenStorage(),
            tenant_id="t1",
            graph_file_id=None,
            doc={"file_name": "x.txt", "result": {"f": {"confidence": 0.1}}},
            file_name="x.txt",
            file_hash="h",
        )
    )

    assert count == 0


def test_insert_failure_is_swallowed() -> None:
    storage = _FakeStorage(
        [
            _rule(
                "RULE_LOW_CONFIDENCE",
                {"scope": "field", "path": "confidence", "op": "lt", "value": 0.9},
            )
        ],
        fail_insert=True,
    )

    count = asyncio.run(
        _store_document_alerts(
            storage=storage,
            tenant_id="t1",
            graph_file_id=None,
            doc={"file_name": "x.txt", "result": {"f": {"confidence": 0.1}}},
            file_name="x.txt",
            file_hash="h",
        )
    )

    assert count == 0
