"""Public package exports for mcp-obsidian.

The CLI now lives in ``mcp_obsidian.cli`` to avoid side effects on import.
``pyproject.toml`` script entry can continue referencing ``mcp_obsidian:main``.
"""

from __future__ import annotations

from .cli import main  # re-export

__all__ = ["main"]
