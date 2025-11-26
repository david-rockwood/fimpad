# tests/test_client.py
from __future__ import annotations

from typing import Any

from fimpad import client


class _DummyResponse:
    def __init__(self) -> None:
        self.closed = False

    def iter_lines(self, *, decode_unicode: bool) -> Any:  # pragma: no cover - signature mimic
        yield b'data: {"choices": [{"text": "hello"}]}'

    def close(self) -> None:
        self.closed = True

    def raise_for_status(self) -> None:  # pragma: no cover - no-op for tests
        return None


def test_stream_completion_uses_split_timeouts(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, json: dict, stream: bool, timeout: tuple[int, int]):
        captured["url"] = url
        captured["json"] = json
        captured["stream"] = stream
        captured["timeout"] = timeout
        return _DummyResponse()

    monkeypatch.setattr(client.requests, "post", fake_post)

    pieces = list(client.stream_completion("http://example.com", {"prompt": "x"}))

    assert pieces == ["hello"]
    assert captured["url"] == "http://example.com/v1/completions"
    assert captured["stream"] is True
    assert captured["json"] == {"prompt": "x"}
    assert captured["timeout"] == (client.CONNECT_TIMEOUT, client.READ_TIMEOUT)
