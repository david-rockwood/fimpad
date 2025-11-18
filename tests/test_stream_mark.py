from __future__ import annotations

from fimpad.app import FIMPad


class FakeText:
    def __init__(self, content: str = "") -> None:
        self.content = content
        self.marks: dict[str, int] = {}
        self.gravities: dict[str, str] = {}
        self.last_seen: str | None = None
        self.hidden_marks: set[str] = set()

    def _format_index(self, offset: int) -> str:
        if offset <= 0:
            return "1.0"
        return f"1.0+{offset}c"

    def _parse_index(self, index: str) -> int:
        if index in {"end", "tk.END"}:
            return len(self.content)
        if index in self.marks:
            return self.marks[index]
        if "+" in index:
            base, delta = index.split("+", 1)
            base_offset = self._parse_index(base)
            if delta.endswith("c"):
                return base_offset + int(delta[:-1])
            raise ValueError(f"Unsupported index delta: {index}")
        if "." in index:
            line_str, col_str = index.split(".", 1)
            line_no = int(line_str)
            col = int(col_str)
            lines = self.content.splitlines(keepends=True)
            offset = 0
            for i in range(min(line_no - 1, len(lines))):
                offset += len(lines[i])
            return offset + col
        if index == "1.0":
            return 0
        raise ValueError(f"Unsupported index: {index}")

    def index(self, what: str) -> str:
        if what in self.marks:
            return self._format_index(self.marks[what])
        if what in {"end", "tk.END"}:
            return self._format_index(len(self.content))
        return self._format_index(self._parse_index(what))

    def insert(self, index: str, piece: str) -> None:
        offset = self._parse_index(index)
        normalized = piece.replace("\r\n", "\n").replace("\r", "\n")
        self.content = self.content[:offset] + normalized + self.content[offset:]
        delta = len(normalized)
        for name, pos in list(self.marks.items()):
            if pos > offset or (
                pos == offset and self.gravities.get(name, "right") == "right"
            ):
                self.marks[name] = pos + delta

    def delete(self, start: str, end: str) -> None:
        start_offset = self._parse_index(start)
        end_offset = self._parse_index(end)
        if end_offset < start_offset:
            start_offset, end_offset = end_offset, start_offset
        removed = max(0, end_offset - start_offset)
        if removed == 0:
            return
        self.content = self.content[:start_offset] + self.content[end_offset:]
        for name, pos in list(self.marks.items()):
            if pos > end_offset:
                self.marks[name] = pos - removed
            elif start_offset <= pos <= end_offset:
                self.marks[name] = start_offset

    def mark_set(self, name: str, where: str) -> None:
        self.marks[name] = self._parse_index(where)
        self.gravities.setdefault(name, "right")
        self.last_seen = name

    def mark_gravity(self, name: str, gravity: str) -> None:
        self.gravities[name] = gravity

    def see(self, mark: str) -> None:  # pragma: no cover - trivial
        self.last_seen = mark

    def tag_add(self, name: str, start: str, end: str) -> None:  # pragma: no cover
        pass

    def tag_remove(self, name: str, start: str, end: str) -> None:  # pragma: no cover
        pass

    def dlineinfo(self, mark: str):  # pragma: no cover - minimal stub
        if mark in self.hidden_marks:
            return None
        return (0, 0, 0, 0)


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
        "_stream_follow_primed": False,
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
