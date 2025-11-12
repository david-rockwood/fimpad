"""Utilities for loading the help tab template."""
from __future__ import annotations

from importlib import resources
from typing import Final

_TEMPLATE_PACKAGE: Final[str] = "fimpad.data"
_TEMPLATE_NAME: Final[str] = "help_tab_template.txt"
_HELP_TEMPLATE: str | None = None


def get_help_template() -> str:
    """Return the cached help tab template text."""
    global _HELP_TEMPLATE
    if _HELP_TEMPLATE is None:
        data_path = resources.files(_TEMPLATE_PACKAGE).joinpath(_TEMPLATE_NAME)
        _HELP_TEMPLATE = data_path.read_text(encoding="utf-8")
    return _HELP_TEMPLATE


__all__ = ["get_help_template"]
