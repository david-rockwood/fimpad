# fimpad/utils.py
from __future__ import annotations


def offset_to_tkindex(content: str, offset: int) -> str:
    """Convert a Python-string offset to a Tk index using UTF-16 code units."""

    if offset <= 0:
        return "1.0"

    prefix = content[:offset]
    line_no = prefix.count("\n") + 1
    last_newline = prefix.rfind("\n")
    col_text = prefix if last_newline == -1 else prefix[last_newline + 1 :]

    col_units = len(col_text.encode("utf-16-le")) // 2
    return f"{line_no}.{col_units}"
