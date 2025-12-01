import queue
import sys
from types import SimpleNamespace


class _DummyEnchant:
    class errors:
        class DictNotFoundError(Exception):
            pass

    @staticmethod
    def Dict(lang):
        return SimpleNamespace(check=lambda _: True, suggest=lambda _: [])


# Ensure the enchant stub is registered before importing the application module.
sys.modules.setdefault("enchant", _DummyEnchant())

from fimpad.app import FIMPad  # noqa: E402


class DummyText:
    def __init__(self, text):
        self._text = text

    def tag_remove(self, *args, **kwargs):
        # used by _schedule_spellcheck_for_frame when spellcheck is disabled
        self.removed = (args, kwargs)

    def get(self, start, end):
        if start != "1.0" or end != "end-1c":
            raise AssertionError("Unexpected indices requested from DummyText")
        return self._text


class DummyScrollableText:
    def __init__(self, text, visible_lines=1):
        self._text = text
        self.visible_lines = visible_lines
        self._lines = text.split("\n") or [""]

    def _split_index(self, index_str):
        line_str, col_str = index_str.split(".")
        return int(line_str), int(col_str)

    def _index_to_offset(self, index_str):
        line, col = self._split_index(index_str)
        line = max(1, min(line, len(self._lines)))
        col = max(0, col)
        offset = 0
        for idx, ln in enumerate(self._lines, start=1):
            if idx < line:
                offset += len(ln) + 1  # include newline
            elif idx == line:
                offset += min(col, len(ln))
                break
        return min(offset, len(self._text))

    def _offset_to_index(self, offset):
        remaining = max(0, min(offset, len(self._text)))
        for idx, ln in enumerate(self._lines, start=1):
            line_len = len(ln)
            if remaining <= line_len:
                return f"{idx}.{remaining}"
            remaining -= line_len
            if remaining == 0:
                return f"{idx}.{line_len}"
            remaining -= 1  # newline
        last_line = len(self._lines)
        last_col = len(self._lines[-1])
        return f"{last_line}.{last_col}"

    def index(self, spec):
        if spec == "end-1c":
            return self._offset_to_index(len(self._text))
        if spec.endswith(".end"):
            line = int(spec.split(".")[0])
            line = max(1, min(line, len(self._lines)))
            return f"{line}.{len(self._lines[line - 1])}"
        if spec.startswith("@0,"):
            visible_line = min(len(self._lines), self.visible_lines)
            return f"{visible_line}.0"
        if "+" in spec and spec.endswith("c"):
            base, inc = spec.split("+")
            base_idx = self.index(base)
            offset = self._index_to_offset(base_idx) + int(inc[:-1])
            return self._offset_to_index(offset)
        if "." in spec:
            return spec
        raise AssertionError(f"Unhandled index spec: {spec}")

    def count(self, start, end, *_):
        return (self._index_to_offset(end) - self._index_to_offset(start),)

    def get(self, start, end):
        return self._text[self._index_to_offset(start) : self._index_to_offset(end)]

    def winfo_height(self):
        return self.visible_lines

    def tag_remove(self, *args, **kwargs):
        self.removed = (args, kwargs)


class ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class FakeDict:
    def __init__(self, *, misspelled=None):
        self.misspelled = set(misspelled or [])
        self.checked = []

    def check(self, word):
        self.checked.append(word)
        return word not in self.misspelled

    def suggest(self, word):  # parity with enchant.Dict API
        return [f"{word}_suggestion"]


def _make_dummy_app(text, *, dictionary=None):
    dummy_frame = object()
    dummy_app = SimpleNamespace()
    dummy_app.tabs = {dummy_frame: {"text": DummyText(text)}}
    dummy_app._result_queue = queue.Queue()
    dummy_app.cfg = {"spell_lang": "en_US", "spellcheck_enabled": True}
    dummy_app._spell_ignore = set()
    dummy_app.nb = SimpleNamespace(select=lambda: dummy_frame)
    dummy_app._dictionary = dictionary
    return dummy_app, dummy_frame


def test_spellcheck_handles_contractions(monkeypatch):
    text = "I couldn't believe she shouldn't be here."
    dummy_app, dummy_frame = _make_dummy_app(text, dictionary=FakeDict())

    monkeypatch.setattr("fimpad.app.threading.Thread", ImmediateThread)

    FIMPad._spawn_spellcheck(dummy_app, dummy_frame)

    output = dummy_app._result_queue.get_nowait()
    assert output["spans"] == []

    words = set(dummy_app._dictionary.checked)
    assert "couldn't" in words
    assert "shouldn't" in words
    assert "couldn" not in words
    assert "shouldn" not in words


def test_spellcheck_marks_misspellings(monkeypatch):
    text = "Good wurd here"
    fake_dict = FakeDict(misspelled={"wurd"})
    dummy_app, dummy_frame = _make_dummy_app(text, dictionary=fake_dict)

    monkeypatch.setattr("fimpad.app.threading.Thread", ImmediateThread)

    FIMPad._spawn_spellcheck(dummy_app, dummy_frame)

    output = dummy_app._result_queue.get_nowait()
    assert output["spans"] == [("1.5", "1.9")]
    assert set(fake_dict.checked) == {"here", "Good", "wurd"}


def test_dictionary_init_failure_disables_spellcheck(monkeypatch):
    notifications = []
    dummy_app = SimpleNamespace(
        cfg={"spellcheck_enabled": True},
        _spell_notice_msg=None,
        _spell_notice_last=None,
        _notify_spell_unavailable=lambda: notifications.append("called"),
        tabs={},
    )

    monkeypatch.setattr(
        "fimpad.app.enchant.Dict",
        lambda lang: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    dictionary = FIMPad._load_dictionary(dummy_app, "en_US")
    assert dictionary is None
    assert dummy_app._spell_notice_msg == "Spellcheck unavailable: failed to initialize dictionary."
    assert notifications == ["called"]

    # Ensure scheduling gracefully removes tags without a dictionary
    dummy_frame = object()
    dummy_app.tabs[dummy_frame] = {"text": DummyText("ok")}
    dummy_app._dictionary = None
    FIMPad._schedule_spellcheck_for_frame(dummy_app, dummy_frame)
    assert dummy_app.tabs[dummy_frame]["_spell_timer"] is None


def test_spell_region_respects_char_budget():
    long_line = "a" * 500
    dummy_app = SimpleNamespace(
        cfg={
            "spellcheck_full_document_line_threshold": 10,
            "spellcheck_view_buffer_lines": 0,
            "spellcheck_max_chars": 100,
        }
    )
    dummy_app._clamp_region_to_budget = FIMPad._clamp_region_to_budget.__get__(
        dummy_app, FIMPad
    )
    dummy_app._spell_viewport_region = FIMPad._spell_viewport_region.__get__(
        dummy_app, FIMPad
    )
    dummy_app._count_text_chars = FIMPad._count_text_chars
    text = DummyScrollableText(long_line, visible_lines=1)

    start_idx, end_idx, base_line, base_col = FIMPad._spell_region_for_text(
        dummy_app, text
    )

    assert start_idx == "1.0"
    assert end_idx == "1.100"
    assert base_line == 1
    assert base_col == 0
