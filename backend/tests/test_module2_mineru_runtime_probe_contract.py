from __future__ import annotations

from app.modules.module2.core.integration.mineru_layout import MineruLayoutExtractor


def test_mineru_runtime_probe_script_checks_table_runtime_when_enabled(tmp_path) -> None:
    extractor = MineruLayoutExtractor(cache_dir=str(tmp_path), enable_table=True)

    script = extractor._build_runtime_probe_script()

    assert "import torch" in script
    assert "utils_table_line_rec" in script
    assert "mineru_runtime_probe_ok" in script


def test_mineru_runtime_probe_script_skips_table_runtime_when_disabled(tmp_path) -> None:
    extractor = MineruLayoutExtractor(cache_dir=str(tmp_path), enable_table=False)

    script = extractor._build_runtime_probe_script()

    assert "import torch" in script
    assert "utils_table_line_rec" not in script
    assert "mineru_runtime_probe_ok" in script
