"""Gateway services package.

Keep package import side effects minimal to avoid circular imports during
compat-path aliasing. Import concrete modules from ``app.services.*``.
"""

__all__ = [
    "assistant_prompting",
    "assistant_service",
    "auth_service",
    "extraction_service",
    "frontend_static_service",
    "gateway_service",
    "module1_placeholder_service",
]
