"""Backward-compatible import surface for the unified app factory."""

from app.factory import create_app

__all__ = ["create_app"]
