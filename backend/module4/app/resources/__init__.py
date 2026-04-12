"""Module4 resources namespace."""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = (APP_ROOT.parent / "assets" / "prompts").resolve()

__all__ = ["APP_ROOT", "PROMPTS_DIR"]

