from __future__ import annotations

from typing import Literal


SourceType = Literal["module2"]
JobType = Literal["ingest", "rebuild_graph", "run_rules", "simulate"]
JobStatus = Literal["queued", "running", "success", "failed", "cancelled"]
AlertSeverity = Literal["yellow", "orange", "red"]
AlertStatus = Literal["open", "ack", "resolved", "false_positive"]
RuleKind = Literal["deterministic"]
GraphRAGQueryMode = Literal["local", "global", "drift", "basic"]

