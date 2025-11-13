"""Utilities for loading the help tab template."""
from __future__ import annotations

from importlib import resources
from typing import Final

from . import data as _help_data

_TEMPLATE_NAME: Final[str] = "help_tab_template.txt"
_FALLBACK_TEMPLATE: Final[str] = """[[[system]]]
You are an AI pair programmer embedded in FimPad.
Provide concise, practical guidance tailored to the project the user is editing.
Ask clarifying questions when requirements are unclear and share useful shortcuts when appropriate.

[[[user]]]

[[[/user]]]
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
