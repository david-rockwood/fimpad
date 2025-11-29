from __future__ import annotations

import json
import sys
import types


class _StubEnchant:
    class errors:
        class DictNotFoundError(Exception):
            pass

    @staticmethod
    def Dict(lang):  # pragma: no cover - test helper only
        return types.SimpleNamespace(check=lambda _w: True, suggest=lambda _w: [])


sys.modules.setdefault("enchant", _StubEnchant())

from fimpad.app import FIMPad
from fimpad.parser import FIMRequest, TagToken


def _make_request(*, use_completion: bool) -> FIMRequest:
    marker = TagToken(start=0, end=0, raw="[[[/assistant]]]", body="", tag=None)
    return FIMRequest(
        marker=marker,
        prefix_token=None,
        suffix_token=None,
        before_region="prefix text",
        after_region="after",
        safe_suffix="suffix text",
        max_tokens=10,
        keep_tags=False,
        stop_patterns=[],
        chop_patterns=[],
        post_functions=(),
        prepend_actions=(),
        config_overrides={},
        use_completion=use_completion,
    )


def _stub_app() -> FIMPad:
    app = object.__new__(FIMPad)
    app.cfg = {
        "fim_prefix": "<PRE>",
        "fim_suffix": "<SUF>",
        "fim_middle": "<MID>",
        "log_entries_kept": 5,
    }
    app._fim_log = []
    app._log_tab_frame = None
    app._refresh_log_tab_contents = lambda: None
    return app


def test_log_includes_mode_for_completion_generation():
    app = _stub_app()
    request = _make_request(use_completion=True)

    app._log_fim_generation(request, response="hello")

    assert len(app._fim_log) == 1
    payload = json.loads(app._fim_log[-1])
    assert payload["mode"] == "completion generation"
    assert payload["prefix"] == "prefix text"
    assert payload["suffix"] == "suffix text"


def test_log_includes_mode_for_fim_generation():
    app = _stub_app()
    request = _make_request(use_completion=False)

    app._log_fim_generation(request, response="hello")

    payload = json.loads(app._fim_log[-1])
    assert payload["mode"] == "FIM generation"
    assert payload["prefix"] == "<PRE>prefix text"
    assert payload["suffix"] == "<SUF>suffix text<MID>"
