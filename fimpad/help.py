# ruff: noqa: E501
"""Utilities for loading the help tab template."""
from __future__ import annotations

from importlib import resources
from typing import Final

from . import data as _help_data

_TEMPLATE_NAME: Final[str] = "help_tab_template.txt"
_FALLBACK_TEMPLATE: Final[str] = """FIMpad Help
============

Welcome to FIM-only mode. Insert a triple-bracket marker like `[[[120]]]` where you want text generated. Use [[[prefix]]] and [[[suffix]]] tags to bound the context that should be sent to the model.
"""
_HELP_TEMPLATE: str | None = None


def get_help_template() -> str:
    """Return the cached help tab template text."""
    global _HELP_TEMPLATE
    if _HELP_TEMPLATE is None:
        try:
            data_path = resources.files(_help_data).joinpath(_TEMPLATE_NAME)
            _HELP_TEMPLATE = data_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _HELP_TEMPLATE = _FALLBACK_TEMPLATE
    return _HELP_TEMPLATE


__all__ = ["get_help_template"]
