from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_policy_bundle_module = import_module("module2.app.bootstrap.policy")


def test_build_module2_main_policy_bundle_exposes_expected_policy_helpers(tmp_path: Path) -> None:
    env_values = {
        "MODULE2_ARTIFACT_ROOT_DIR": str(tmp_path / "artifacts"),
        "MODULE2_EXTRACT_JOB_STATE_DIR": str(tmp_path / "job_state"),
        "MODULE2_DOC_TO_PDF_ENABLE": "true",
        "MODULE2_WORD_PARSE_VIA_PDF": "true",
        "MODULE2_VISUAL_STRICT": "true",
        "MODULE2_REQUIRE_VISUAL_CHAIN": "true",
        "MODULE2_DISABLE_FASTTRACK_FALLBACK": "true",
        "MODULE2_DISABLE_QUICK_TABLE_FALLBACK": "true",
        "MODULE2_DOCX_NATIVE_RECOVERY_ENABLE": "false",
        "MODULE2_OFFICE_PREVIEW_TIMEOUT_SEC": "123",
    }

    bundle = main_policy_bundle_module.build_module2_main_policy_bundle(
        module2_root=Path("backend/module2"),
        getenv=lambda name, default=None: env_values.get(name, default),
        build_module2_llm_provider_fn=lambda **kwargs: kwargs,
    )

    assert bundle.artifact_root_dir().exists()
    assert bundle.extraction_job_state_root_dir().exists()
    assert bundle.office_preview_timeout_sec() == 123.0
    assert bundle.office_convert_enabled() is True
    assert bundle.word_pdf_required() is True
    assert bundle.visual_strict_mode() is True
    assert bundle.visual_chain_required() is True
    assert bundle.disable_fasttrack_fallback() is True
    assert bundle.disable_quick_table_fallback() is True
    assert bundle.docx_native_recovery_enabled() is False
    assert bundle.build_preflight_provider(9.0)["timeout_sec"] == 9.0
    assert bundle.provider_unavailable_http_exception(RuntimeError("boom")).status_code == 503
