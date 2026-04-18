"""Module2 service package.

Intentionally avoids package-level re-exports so imports stay explicit and
do not trigger heavyweight module loading during composition bootstrap.
"""

__all__: list[str] = []
