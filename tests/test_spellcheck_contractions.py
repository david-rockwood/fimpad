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
