"""Utilities for tokenizing triple-bracket FIM markers."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from .config import MARKER_REGEX

TRIPLE_RE = re.compile(r"\[\[\[(?P<body>.*?)\]\]\]", re.DOTALL)


@dataclass(frozen=True)
class TextToken:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class TagToken:
    start: int
    end: int
    raw: str
    body: str
    kind: str
    name: str | None = None
    is_close: bool = False


Token = TextToken | TagToken


def parse_triple_tokens(content: str) -> Iterator[Token]:
    """Yield tokens for ``content`` splitting around ``[[[...]]]`` regions."""
    last_index = 0
    for match in TRIPLE_RE.finditer(content):
        start, end = match.span()
        if start > last_index:
            yield TextToken(start=last_index, end=start, text=content[last_index:start])
        raw = match.group(0)
        inner = match.group("body") or ""
        marker_match = MARKER_REGEX.fullmatch(raw)
        if marker_match:
            body = marker_match.group("body") or ""
            yield TagToken(
                start=start,
                end=end,
                raw=raw,
                body=body,
                kind="marker",
            )
        else:
            token = _classify_tag(raw, inner, start, end)
            yield token
        last_index = end
    if last_index < len(content):
        yield TextToken(start=last_index, end=len(content), text=content[last_index:])


def _classify_tag(
    raw: str,
    inner: str,
    start: int,
    end: int,
) -> TagToken:
    body = inner.strip()
    if not body:
        return TagToken(start=start, end=end, raw=raw, body=body, kind="unknown")

    is_close = False
    if body.startswith("/"):
        is_close = True
        body = body[1:].lstrip()

    name = body.strip()
    name_key = name.casefold()

    if name_key in {"prefix", "suffix"}:
        return TagToken(
            start=start,
            end=end,
            raw=raw,
            body=name,
            kind=name_key,
            name=name_key,
            is_close=is_close,
        )

    return TagToken(
        start=start,
        end=end,
        raw=raw,
        body=name,
        kind="unknown",
        name=name_key if name_key else None,
        is_close=is_close,
    )


__all__ = [
    "Token",
    "TextToken",
    "TagToken",
    "parse_triple_tokens",
]
