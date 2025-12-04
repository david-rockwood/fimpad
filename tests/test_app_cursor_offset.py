import tkinter as tk

from fimpad.app import _cursor_offset_from_text_widget


class DummyText:
    def __init__(self, content: str, cursor_offset: int):
        self.content = content
        self.cursor_offset = cursor_offset

    def get(self, start: str, end: str) -> str:
        assert start == "1.0"
        assert end == tk.INSERT
        return self.content[: self.cursor_offset]


def test_cursor_offset_counts_emoji_as_single_character():
    content = "### 🔹 **Shipwrecked**\n[[[1000]]]"
    cursor_offset = content.index("[[[")

    dummy_text = DummyText(content, cursor_offset)

    assert _cursor_offset_from_text_widget(dummy_text) == cursor_offset


def test_cursor_offset_returns_none_on_widget_error():
    class BrokenText:
        def get(self, start: str, end: str) -> str:
            raise RuntimeError("boom")

    assert _cursor_offset_from_text_widget(BrokenText()) is None
