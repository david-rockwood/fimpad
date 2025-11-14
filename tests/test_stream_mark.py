from __future__ import annotations

from fimpad.app import FIMPad


class FakeText:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.marks: dict[str, int] = {}
        self.gravities: dict[str, str] = {}
        self.last_seen: str | None = None

    def _format_index(self, offset: int) -> str:
        if offset <= 0:
            return "1.0"
        return f"1.0+{offset}c"

    def _parse_index(self, index: str) -> int:
        if index in {"end", "tk.END"}:
            return len(self.content)
        if index == "1.0":
            return 0
        if index.startswith("1.0+") and index.endswith("c"):
            return int(index[4:-1])
        if index in self.marks:
            return self.marks[index]
        raise ValueError(f"Unsupported index: {index}")

    def index(self, what: str) -> str:
        if what in self.marks:
            return self._format_index(self.marks[what])
        if what in {"end", "tk.END"}:
            return self._format_index(len(self.content))
        raise ValueError(f"Unknown mark: {what}")

    def insert(self, index: str, piece: str) -> None:
        offset = self._parse_index(index)
        normalized = piece.replace("\r\n", "\n").replace("\r", "\n")
        self.content = self.content[:offset] + normalized + self.content[offset:]
        delta = len(normalized)
        for name, pos in list(self.marks.items()):
            if pos > offset:
                self.marks[name] = pos + delta
            elif pos == offset and self.gravities.get(name, "right") == "right":
                self.marks[name] = pos + delta

    def mark_set(self, name: str, index: str) -> None:
        self.marks[name] = self._parse_index(index)

    def mark_gravity(self, name: str, gravity: str) -> None:
        self.gravities[name] = gravity

    def see(self, mark: str) -> None:  # pragma: no cover - debug aid
        self.last_seen = mark


def test_flush_stream_buffer_respects_right_gravity():
    app = object.__new__(FIMPad)
    frame = object()
    text = FakeText("[[[/assistant]]]")
    text.mark_set("stream_here", "1.0")
    text.mark_gravity("stream_here", "right")

    st = {
        "text": text,
        "stream_buffer": ["foo", "\r\n", "bar"],
        "dirty": False,
    }

    app.tabs = {frame: st}
    app._should_follow = lambda widget: False

    def _set_dirty(state, dirty):
        state["dirty"] = dirty

    app._set_dirty = _set_dirty

    app._flush_stream_buffer(frame, "stream_here")

    assert st["stream_buffer"] == []
    assert text.content == "foo\nbar[[[/assistant]]]"
    assert text.marks["stream_here"] == text.content.index("[[[/assistant]]]")
    assert st["dirty"] is True
