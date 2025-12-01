# fimpad/client.py
from __future__ import annotations

import json
import threading
from collections.abc import Iterable

import requests

CONNECT_TIMEOUT = 10
READ_TIMEOUT = 7200


def _sse_chunks(resp, stop_event: threading.Event | None = None) -> Iterable[str]:
    # decode lines as UTF-8, accept "data:" with/without a space
    try:
        for raw in resp.iter_lines(decode_unicode=False):
            if stop_event is not None and stop_event.is_set():
                resp.close()
                break
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace")
            except Exception:
                continue
            if not line.startswith("data:"):
                continue
            data_str = line[5:].lstrip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue
            ch0 = (chunk.get("choices") or [{}])[0]
            piece = (
                ch0.get("delta", {}).get("content", "")
                or ch0.get("message", {}).get("content", "")
                or ch0.get("text", "")
            )
            if piece:
                yield piece
    except Exception:
        # When a stop event triggers `resp.close()` mid-stream, the underlying
        # HTTP connection may already be torn down by the time `iter_lines`
        # attempts to read again. Treat this as a graceful stop so the caller
        # doesn't surface spurious errors to the UI.
        if stop_event is not None and stop_event.is_set():
            return
        raise


def stream_completion(
    endpoint: str, payload: dict, stop_event: threading.Event | None = None
) -> Iterable[str]:
    url = f"{endpoint}/v1/completions"
    resp = requests.post(
        url,
        json=payload,
        stream=True,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    closer_thread = None
    try:
        resp.raise_for_status()
        if stop_event is not None:
            closer_thread = threading.Thread(
                target=lambda: (stop_event.wait(), resp.close()),
                daemon=True,
            )
            closer_thread.start()

        yield from _sse_chunks(resp, stop_event)
    finally:
        resp.close()
        if closer_thread is not None and closer_thread.is_alive():
            stop_event.set()
