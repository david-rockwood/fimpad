"""Helpers for handling stream stop/chop patterns.

These utilities are pure functions so they can be unit-tested without the
tkinter event loop used by :mod:`fimpad.app`.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class StreamMatch:
    """Information about a matched stop/chop pattern in a stream chunk."""

    pattern: str
    action: str
    match_index: int
    end_index: int


def find_stream_match(text: str, patterns: Iterable[dict[str, str]]) -> StreamMatch | None:
    """Locate the earliest pattern match in ``text``.

    Returns the match with the lowest character offset. When multiple patterns
    match at the same offset, the one that appeared first in ``patterns`` wins.
    """

    best: tuple[int, int] | None = None  # (match_index, order)
    best_pattern: dict[str, str] | None = None

    for order, patt in enumerate(patterns):
        patt_text = patt.get("text", "")
        if not patt_text:
            continue
        idx = text.find(patt_text)
        if idx == -1:
            continue
        cand = (idx, order)
        if best is None or cand < best:
            best = cand
            best_pattern = patt

    if best is None or best_pattern is None:
        return None

    match_index = best[0]
    patt_text = best_pattern.get("text", "")
    action = best_pattern.get("action", "stop")

    return StreamMatch(
        pattern=patt_text,
        action=action,
        match_index=match_index,
        end_index=match_index + len(patt_text),
    )


def compute_stream_tail(tail: str, piece: str, patterns: Iterable[dict[str, str]]) -> str:
    """Compute the carry-over tail for the next stream chunk.

    The tail is the longest possible prefix needed to match any pattern that
    may span chunk boundaries (max pattern length minus one character).
    """

    maxlen = max((len(p.get("text", "")) for p in patterns), default=0)
    if maxlen <= 0:
        return ""

    keep = maxlen - 1
    if keep <= 0:
        return ""

    combined = tail + piece
    return combined[-keep:]
