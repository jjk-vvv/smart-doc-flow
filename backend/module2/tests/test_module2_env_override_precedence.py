from __future__ import annotations

from pathlib import Path


def test_module2_base_env_loading_does_not_override_process_env() -> None:
    module2_root = Path(__file__).resolve().parents[1]
    target_files = [
        module2_root / "app" / "composition" / "application.py",
        module2_root / "app" / "assistant_1" / "config.py",
        module2_root / "app" / "integrations" / "llm" / "provider.py",
        module2_root / "app" / "core" / "parsers" / "native_document_parser.py",
    ]

    for path in target_files:
        source = path.read_text(encoding="utf-8")
        assert 'load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)' in source
        assert "override=not bool(CUSTOM_MODULE2_ENV_FILE)" not in source
