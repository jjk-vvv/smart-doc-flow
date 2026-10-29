from __future__ import annotations

from app.modules.module2.core.table.numeric_statistics import quantile


def test_quantile_handles_empty_and_single_value_samples() -> None:
    assert quantile([], 0.5) is None
    assert quantile([7], 0.05) == 7


def test_quantile_interpolates_unsorted_samples_and_clamps_boundaries() -> None:
    assert quantile([30, 0, 20, 10], 0.25) == 7.5
    assert quantile([30, 0, 20, 10], -1) == 0
    assert quantile([30, 0, 20, 10], 2) == 30
