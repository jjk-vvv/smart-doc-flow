from __future__ import annotations

from importlib import import_module


runtime_module = import_module("app.modules.module2.services.document.tools")
TraceSemanticsRuntime = runtime_module.TraceSemanticsRuntime


def test_trace_semantics_runtime_infers_display_kind_from_figure_payload() -> None:
    runtime = TraceSemanticsRuntime()

    assert runtime.display_kind_from_hit({"object_type": "field"}) == "field"
    assert runtime.display_kind_from_hit({"object_type": "table"}) == "table"
    assert runtime.display_kind_from_hit({"object_type": "unknown"}) == "other"
    assert runtime.display_kind_from_hit(
        {"object_type": "figure", "locator": {"figure_type": "table"}}
    ) == "table"
    assert runtime.display_kind_from_hit(
        {
            "object_type": "figure",
            "locator": {
                "dataframe": {"headers": ["A"], "rows": [["1"]]},
                "content_modes": [],
            },
        }
    ) == "table"
    assert runtime.display_kind_from_hit(
        {
            "object_type": "figure",
            "locator": {
                "dataframe": {"headers": ["A"], "rows": [["1"]]},
                "content_modes": ["visual"],
            },
        }
    ) == "image"


def test_trace_semantics_runtime_builds_trace_stats() -> None:
    runtime = TraceSemanticsRuntime()

    stats = runtime.build_trace_stats(
        [
            {"object_type": "field", "page": 1},
            {
                "object_type": "figure",
                "page": 2,
                "locator": {"dataframe": {"headers": ["A"], "rows": [["1"]]}, "content_modes": []},
            },
            {"object_type": "figure", "page": "x", "locator": {}},
        ]
    )

    assert stats == {
        "trace_hit_count": 3,
        "trace_object_counts": {"field": 1, "figure": 2},
        "trace_display_counts": {"field": 1, "table": 1, "image": 1},
        "trace_pages": [1, 2],
    }
