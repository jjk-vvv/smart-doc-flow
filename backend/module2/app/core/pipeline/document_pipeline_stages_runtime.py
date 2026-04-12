"""Re-export shim: document_pipeline_stages_runtime.

All classes are defined in document_pipeline_runtime.py.
This module exists for backward compatibility with tests written
against the pre-merge module structure (March 2026 medium-grain consolidation).

Uses importlib-based loading so this file works both as a regular package
module (normal import) and when loaded standalone via
importlib.util.spec_from_file_location (as done by the test suite).
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_RUNTIME_PATH = _THIS_DIR / "document_pipeline_runtime.py"
_MODULE_KEY = "_smart_doc_flow_module2_document_pipeline_runtime_canonical"

if _MODULE_KEY not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE_KEY, _RUNTIME_PATH)
    assert _spec and _spec.loader
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_KEY] = _mod
    _spec.loader.exec_module(_mod)

_pipeline_runtime = sys.modules[_MODULE_KEY]

DocumentParseAttemptRuntime = _pipeline_runtime.DocumentParseAttemptRuntime
DocumentPipelineFinalizeRuntime = _pipeline_runtime.DocumentPipelineFinalizeRuntime
DocumentPipelineGraphRuntime = _pipeline_runtime.DocumentPipelineGraphRuntime
DocumentPipelineInputRuntime = _pipeline_runtime.DocumentPipelineInputRuntime
DocumentPipelineOutcome = _pipeline_runtime.DocumentPipelineOutcome
DocumentPipelineParseRuntime = _pipeline_runtime.DocumentPipelineParseRuntime
DocumentPipelineSchemaRuntime = _pipeline_runtime.DocumentPipelineSchemaRuntime
ParsePreparationRuntime = _pipeline_runtime.ParsePreparationRuntime

__all__ = [
    "DocumentParseAttemptRuntime",
    "DocumentPipelineFinalizeRuntime",
    "DocumentPipelineGraphRuntime",
    "DocumentPipelineInputRuntime",
    "DocumentPipelineOutcome",
    "DocumentPipelineParseRuntime",
    "DocumentPipelineSchemaRuntime",
    "ParsePreparationRuntime",
]
