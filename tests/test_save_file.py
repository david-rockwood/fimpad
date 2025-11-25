from __future__ import annotations

import sys
import tkinter as tk
import types

FakeDictNotFoundError = type("FakeDictNotFoundError", (Exception,), {})

fake_enchant = types.SimpleNamespace(
    Dict=lambda *_args, **_kwargs: None,
    dict_exists=lambda _lang: True,
    list_languages=lambda: [],
    errors=types.SimpleNamespace(DictNotFoundError=FakeDictNotFoundError),
)
sys.modules.setdefault("enchant", fake_enchant)

from fimpad.app import FIMPad  # noqa: E402


class FakeText:
    def __init__(self, content: str):
        self.content = content
        self.modified = True

    def get(self, start: str, end: str) -> str:  # pragma: no cover - trivial
        if end == tk.END:
            return f"{self.content}\n"
        return self.content

    def edit_modified(self, value: bool) -> None:
        self.modified = value


def test_save_file_omits_tk_sentinel_newline(tmp_path):
    file_path = tmp_path / "note.txt"
    text = FakeText("hello")

    app = FIMPad.__new__(FIMPad)
    app._current_tab_state = lambda: {"path": file_path, "text": text}  # type: ignore[attr-defined]
    app._set_dirty = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]
    app._show_error = lambda *_args, **_kwargs: None  # type: ignore[attr-defined]

    FIMPad._save_file_current(app)

    assert file_path.read_text(encoding="utf-8") == "hello"
    assert text.modified is False
