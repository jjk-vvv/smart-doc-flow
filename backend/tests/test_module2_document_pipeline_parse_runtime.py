from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace


document_pipeline_parse_runtime_module = importlib.import_module("app.modules.module2.core.pipeline.document_pipeline_stages_runtime")
DocumentPipelineParseRuntime = document_pipeline_parse_runtime_module.DocumentPipelineParseRuntime


class _Logger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def info(self, message: str, *args) -> None:
        self.calls.append((message, args))


class _ParsePreparationRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def prepare(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            parse_timeout_sec=100.0,
            extract_timeout_sec=160.0,
            parse_warning="parse-warning",
            parse_source_file_name="source.docx",
            parse_source_file_bytes=b"docx",
            progress_message="parsing",
            progress_extra={"stage": "parsing"},
            parse_attempt_runner="runner",
        )


class _DocumentParseRecoveryRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            marked_markdown="markdown",
            bbox_map={"r1": [1.0]},
            table_blocks=[{"table_id": "t1"}],
            figure_blocks=[{"figure_id": "f1"}],
            parse_stats={"pipeline": "visual_first", "chain_status": "success"},
            parse_track="VisualTrack",
            parse_warning="recovery-warning",
        )


class _PerfCounter:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        if len(self._values) == 1:
            return self._values[0]
        return self._values.pop(0)


async def _emit_progress(*args, **kwargs):
    return None


def test_document_pipeline_parse_runtime_executes_parse_handoff() -> None:
    runtime = DocumentPipelineParseRuntime(perf_counter=_PerfCounter([101.25]))
    parse_preparation_runtime = _ParsePreparationRuntime()
    document_parse_recovery_runtime = _DocumentParseRecoveryRuntime()
    logger = _Logger()

    outcome = asyncio.run(
        runtime.execute(
            file_name="demo.docx",
            file_bytes=b"docx",
            parse_input_name="demo.pdf",
            parse_input_bytes=b"%PDF",
            parse_track="VisualTrack",
            parse_warning="word-warning",
            parse_timeout_sec=120.0,
            extract_timeout_sec=180.0,
            nonpdf_total_budget_sec=240.0,
            nonpdf_guard_sec=2.0,
            started_at_sec=50.0,
            parse_started_at_sec=100.0,
            input_is_word=True,
            word_suffix=".docx",
            emit_progress=_emit_progress,
            loop="loop",
            parse_preparation_runtime=parse_preparation_runtime,
            document_parse_recovery_runtime=document_parse_recovery_runtime,
            tighten_parse_budgets_before_parse=lambda **kwargs: SimpleNamespace(
                parse_timeout_sec=kwargs["parse_timeout_sec"],
                extract_timeout_sec=kwargs["extract_timeout_sec"],
                tightened=False,
                warning="",
            ),
            build_parse_session=lambda **kwargs: {
                "parse_timeout_sec": kwargs["parse_timeout_sec"],
                "progress_message": "parsing",
                "progress_extra": {"track": kwargs["parse_track"]},
                "parse_source_file_name": kwargs["file_name"],
                "parse_source_file_bytes": kwargs["file_bytes"],
            },
            build_parse_attempt_runner=lambda **kwargs: "runner",
            acquire_parse_execution_slots=lambda track: SimpleNamespace(),
            run_parse_in_process_pool=lambda **kwargs: None,
            run_with_progress_heartbeat=lambda awaitable, **kwargs: awaitable,
            resolve_parse_progress_ramp_sec=lambda **kwargs: 1.0,
            unpack_parse_output=lambda payload: payload,
            visual_parse_policy_runtime=SimpleNamespace(),
            parse_fallback_coordinator_runtime=SimpleNamespace(),
            docx_native_recovery_runtime=SimpleNamespace(),
            fasttrack_fallback_runtime=SimpleNamespace(),
            is_word_file=lambda file_name: file_name.lower().endswith(".docx"),
            visual_chain_required=lambda: True,
            docx_native_recovery_enabled=lambda: True,
            visual_strict_mode=lambda: True,
            disable_fasttrack_fallback=lambda: False,
            logger=logger,
        )
    )

    assert parse_preparation_runtime.calls[0]["parse_input_name"] == "demo.pdf"
    assert document_parse_recovery_runtime.calls[0]["parse_source_file_name"] == "source.docx"
    assert outcome.parse_timeout_sec == 100.0
    assert outcome.extract_timeout_sec == 160.0
    assert outcome.marked_markdown == "markdown"
    assert outcome.parse_track == "VisualTrack"
    assert outcome.parse_warning == "recovery-warning"
    assert outcome.parse_ms == 1250
    assert len(logger.calls) == 1
