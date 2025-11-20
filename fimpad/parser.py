"""Utilities for tokenizing and parsing triple-bracket FIM markers."""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

DEFAULT_MARKER_MAX_TOKENS = 100

TRIPLE_RE = re.compile(r"\[\[\[(?P<body>.*?)\]\]\]", re.DOTALL)
MARKER_REGEX = re.compile(
    r"""
    \[\[\[ \s* (?P<body>
        \d+
        (?: \s*! \s* )?
        (?: \s* (?: "(?:\\.|[^"\\])*" | '(?:\\.|[^'\\])*' ) )*
    ) \s* \]\]\]
    """,
    re.VERBOSE,
)


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


@dataclass(frozen=True)
class FIMRequest:
    """Parsed representation of a FIM marker relative to source text."""

    marker: TagToken
    prefix_token: TagToken | None
    suffix_token: TagToken | None
    before_region: str
    after_region: str
    safe_suffix: str
    max_tokens: int
    keep_tags: bool
    stops_before: list[str]
    stops_after: list[str]
    use_completion: bool


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


def parse_fim_request(
    content: str,
    cursor_offset: int,
    default_n: int = DEFAULT_MARKER_MAX_TOKENS,
) -> FIMRequest | None:
    """Parse FIM instructions around ``cursor_offset``.

    Returns ``None`` when the cursor is not inside a numeric ``[[[N]]]`` marker.
    """

    tokens = list(parse_triple_tokens(content))
    marker_token = _find_marker_token(tokens, cursor_offset)
    if marker_token is None:
        return None

    prefix_token, suffix_token = _find_prefix_suffix(tokens, marker_token)
    before_region, after_region = _extract_regions(
        content, marker_token, prefix_token, suffix_token
    )
    safe_suffix = MARKER_REGEX.sub("", after_region)
    use_completion = after_region.strip() == ""

    marker_body = (marker_token.body or "").strip()
    marker_opts = _parse_marker_body(marker_body, default_n)

    return FIMRequest(
        marker=marker_token,
        prefix_token=prefix_token,
        suffix_token=suffix_token,
        before_region=before_region,
        after_region=after_region,
        safe_suffix=safe_suffix,
        max_tokens=marker_opts.max_tokens,
        keep_tags=marker_opts.keep_tags,
        stops_before=marker_opts.stops_before,
        stops_after=marker_opts.stops_after,
        use_completion=use_completion,
    )


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


@dataclass(frozen=True)
class _MarkerOptions:
    max_tokens: int
    keep_tags: bool
    stops_before: list[str]
    stops_after: list[str]


def _parse_marker_body(body: str, default_n: int) -> _MarkerOptions:
    remainder = body
    token_value: int | str | None = None
    keep_tags = False
    if remainder:
        n_match = re.match(r"(\d+)", remainder)
        if n_match:
            token_value = n_match.group(1)
            remainder = remainder[n_match.end() :]
            bang_match = re.match(r"\s*!\s*", remainder)
            if bang_match:
                keep_tags = True
                remainder = remainder[bang_match.end() :]
            remainder = remainder.strip()
        else:
            remainder = remainder.strip()
    else:
        remainder = ""

    if token_value is None:
        token_value = default_n

    try:
        max_tokens = max(1, min(4096, int(token_value)))
    except Exception:
        max_tokens = default_n

    stops_before: list[str] = []
    stops_after: list[str] = []

    def _unescape_stop(s: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(s):
            c = s[i]
            if c != "\\":
                out.append(c)
                i += 1
                continue
            i += 1
            if i >= len(s):
                out.append("\\")
                break
            esc = s[i]
            i += 1
            if esc == "n":
                out.append("\n")
            elif esc == "t":
                out.append("\t")
            elif esc == "r":
                out.append("\r")
            elif esc == '"':
                out.append('"')
            elif esc == "'":
                out.append("'")
            elif esc == "\\":
                out.append("\\")
            else:
                out.append(esc)
        return "".join(out)

    quote_re = re.compile(r"\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)'")
    for qmatch in quote_re.finditer(remainder):
        double_val = qmatch.group(1)
        single_val = qmatch.group(2)
        if double_val is not None:
            unescaped = _unescape_stop(double_val)
            if unescaped:
                stops_before.append(unescaped)
        elif single_val is not None:
            unescaped = _unescape_stop(single_val)
            if unescaped:
                stops_after.append(unescaped)

    return _MarkerOptions(
        max_tokens=max_tokens,
        keep_tags=keep_tags,
        stops_before=stops_before,
        stops_after=stops_after,
    )


def _find_marker_token(tokens: list[Token], cursor_offset: int) -> TagToken | None:
    marker_token: TagToken | None = None
    for token in tokens:
        if not isinstance(token, TagToken) or token.kind != "marker":
            continue
        if not cursor_within_span(token.start, token.end, cursor_offset):
            continue
        if marker_token is None or token.start >= marker_token.start:
            marker_token = token
    return marker_token


def _find_prefix_suffix(
    tokens: list[Token], marker_token: TagToken
) -> tuple[TagToken | None, TagToken | None]:
    prefix_token: TagToken | None = None
    suffix_token: TagToken | None = None
    for token in tokens:
        if not isinstance(token, TagToken):
            continue
        if token.kind == "prefix" and token.start < marker_token.start:
            prefix_token = token
        elif token.kind == "suffix" and token.start >= marker_token.end:
            suffix_token = token
            break
    return prefix_token, suffix_token


def _extract_regions(
    content: str,
    marker_token: TagToken,
    prefix_token: TagToken | None,
    suffix_token: TagToken | None,
) -> tuple[str, str]:
    if prefix_token is not None:
        pfx_used_end = prefix_token.end
        before_region = content[pfx_used_end:marker_token.start]
    else:
        before_region = content[: marker_token.start]

    if suffix_token is not None:
        sfx_used_start = suffix_token.start
        after_region = content[marker_token.end : sfx_used_start]
    else:
        after_region = content[marker_token.end :]

    return before_region, after_region


def cursor_within_span(start: int, end: int, cursor_offset: int) -> bool:
    return (start <= cursor_offset <= end) or (
        cursor_offset > 0 and start <= cursor_offset - 1 < end
    )


__all__ = [
    "Token",
    "TextToken",
    "TagToken",
    "FIMRequest",
    "MARKER_REGEX",
    "parse_triple_tokens",
    "parse_fim_request",
    "cursor_within_span",
]
