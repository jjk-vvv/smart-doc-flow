from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.modules.module2.agent.graph import ExtractionGraph


def test_module2_agent_graph_text_rules_prefill_intro_and_numeric_fields() -> None:
    markdown = "\n".join(
        [
            '<ref id="text_1">2024 National Economic Report</ref>',
            '<ref id="text_2">issuer: National Statistics Bureau</ref>',
            '<ref id="text_3">publish_date: 2025-02-28</ref>',
            '<ref id="text_4">gdp_total: 1349084</ref>',
            '<ref id="text_5">exports_total: 438468</ref>',
        ]
    )
    bbox_map = {
        "text_1": [1.0, 0.0, 0.0, 1.0, 1.0],
        "text_2": [1.0, 0.0, 0.0, 1.0, 1.0],
        "text_3": [1.0, 0.0, 0.0, 1.0, 1.0],
        "text_4": [1.0, 0.0, 0.0, 1.0, 1.0],
        "text_5": [1.0, 0.0, 0.0, 1.0, 1.0],
    }

    results = ExtractionGraph._apply_text_rule_extraction(
        markdown=markdown,
        target_fields={
            "report_title": "string",
            "issuer": "string",
            "publish_date": "date",
            "gdp_total": "number",
            "exports_total": "number",
        },
        extracted={},
        bbox_map=bbox_map,
    )

    assert results["report_title"]["value"] == "2024 National Economic Report"
    assert results["issuer"]["value"] == "National Statistics Bureau"
    assert results["publish_date"]["value"] == "2025-02-28"
    assert results["gdp_total"]["value"] == 1349084.0
    assert results["exports_total"]["value"] == 438468.0


def test_module2_agent_graph_build_field_extract_batches_uses_larger_plain_text_batches(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MODULE2_FIELD_EXTRACT_BATCH_SIZE", "4")
    monkeypatch.setenv("MODULE2_PLAIN_TEXT_FIELD_EXTRACT_BATCH_SIZE", "12")

    target_fields = {f"field_{index}": "string" for index in range(11)}

    plain_text_batches = ExtractionGraph._build_field_extract_batches(
        target_fields,
        table_blocks=[],
    )
    table_batches = ExtractionGraph._build_field_extract_batches(
        target_fields,
        table_blocks=[{"table_id": "table_1"}],
    )

    assert len(plain_text_batches) == 1
    assert list(plain_text_batches[0].keys()) == list(target_fields.keys())
    assert [len(batch) for batch in table_batches] == [5, 5, 1]
