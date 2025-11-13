import importlib.resources

from fimpad import help as help_module
from fimpad.help import get_help_template


def test_help_template_contains_user_markers():
    template = get_help_template()
    assert "[[[user]]]" in template
    assert "[[[/user]]]" in template


def test_help_template_falls_back_when_resource_missing(monkeypatch):
    monkeypatch.setattr(help_module, "_HELP_TEMPLATE", None)

    def _missing_files(_package):
        raise FileNotFoundError("resource missing")

    monkeypatch.setattr(importlib.resources, "files", _missing_files)

    template = help_module.get_help_template()
    assert template == help_module._FALLBACK_TEMPLATE
