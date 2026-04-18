"""Gateway services package.

Keep package import side effects minimal to avoid circular imports during
compat-path aliasing. Import concrete modules from ``app.services.*``.
"""

__all__ = [
    "assistant_prompting",
    "auth_service",
    "frontend_static_service",
    "gateway_service",
]
