import queue
from types import SimpleNamespace

from fimpad.app import FIMPad


class DummyText:
    def __init__(self, text):
        self._text = text

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


def test_spellcheck_handles_contractions(monkeypatch):
    text = "I couldn't believe she shouldn't be here."
    dummy_frame = object()

    dummy_app = SimpleNamespace()
    dummy_app.tabs = {dummy_frame: {"text": DummyText(text)}}
    dummy_app._result_queue = queue.Queue()
    dummy_app.cfg = {"spell_lang": "en_US"}
    dummy_app._spell_ignore = set()
    dummy_app.nb = SimpleNamespace(select=lambda: dummy_frame)

    monkeypatch.setattr("fimpad.app.threading.Thread", ImmediateThread)

    captured = {}

    def fake_run(cmd, *, input, stdout=None, stderr=None, check=None):
        captured["input"] = input.decode("utf-8")
        return SimpleNamespace(stdout=b"couldn\nshouldn\n")

    monkeypatch.setattr("fimpad.app.subprocess.run", fake_run)

    FIMPad._spawn_spellcheck(dummy_app, dummy_frame)

    output = dummy_app._result_queue.get_nowait()
    assert output["spans"] == []

    words = captured["input"].splitlines()
    assert "couldn't" in words
    assert "shouldn't" in words
    assert "couldn" not in words
    assert "shouldn" not in words
