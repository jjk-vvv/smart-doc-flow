from __future__ import annotations


def quantile(values: list[float], q: float) -> float | None:
    """Return a linearly interpolated quantile, clamping q to [0, 1]."""
    ordered = sorted(float(item) for item in values if isinstance(item, (int, float)))
    if not ordered:
        return None
    position = max(0.0, min(1.0, float(q))) * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
