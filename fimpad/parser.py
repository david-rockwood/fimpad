"""Utilities for tokenizing triple-bracket markers and chat tags."""
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
    role: str | None = None
    is_close: bool = False
    is_star: bool = False


Token = TextToken | TagToken


def parse_triple_tokens(
    content: str, role_aliases: dict[str, str] | None = None
) -> Iterator[Token]:
    """Yield tokens for ``content`` splitting around ``[[[...]]]`` regions.

    ``role_aliases`` should map lowercase role aliases to canonical role names.
    """
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
            token = _classify_tag(raw, inner, start, end, role_aliases or {})
            yield token
        last_index = end
    if last_index < len(content):
        yield TextToken(start=last_index, end=len(content), text=content[last_index:])


def _classify_tag(
    raw: str,
    inner: str,
    start: int,
    end: int,
    role_aliases: dict[str, str],
) -> TagToken:
    body = inner.strip()
    if not body:
        return TagToken(start=start, end=end, raw=raw, body=body, kind="unknown")

    is_close = False
    if body.startswith("/"):
        is_close = True
        body = body[1:].lstrip()

    is_star = False
    if body.endswith("*"):
        is_star = True
        body = body[:-1].rstrip()

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
            is_star=is_star,
        )

    role = _resolve_role(name_key, role_aliases)
    if role:
        return TagToken(
            start=start,
            end=end,
            raw=raw,
            body=name,
            kind="chat",
            name=name_key,
            role=role,
            is_close=is_close,
            is_star=is_star,
        )

    return TagToken(
        start=start,
        end=end,
        raw=raw,
        body=name,
        kind="unknown",
        name=name_key if name_key else None,
        is_close=is_close,
        is_star=is_star,
    )


def _resolve_role(name: str, role_aliases: dict[str, str]) -> str | None:
    role = role_aliases.get(name)
    if role:
        return role
    # Allow lookup against "/alias" entries if callers provide only
    # closing-tag aliases.
    return role_aliases.get(f"/{name}")


__all__ = ["Token", "TextToken", "TagToken", "parse_triple_tokens"]
