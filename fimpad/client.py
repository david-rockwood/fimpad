# fimpad/client.py
from __future__ import annotations

import json
from collections.abc import Iterable

import requests


def _sse_chunks(resp) -> Iterable[str]:
    # decode lines as UTF-8, accept "data:" with/without a space
    for raw in resp.iter_lines(decode_unicode=False):
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


def stream_completion(endpoint: str, payload: dict) -> Iterable[str]:
    url = f"{endpoint}/v1/completions"
    with requests.post(url, json=payload, stream=True, timeout=5000) as resp:
        resp.raise_for_status()
        yield from _sse_chunks(resp)
