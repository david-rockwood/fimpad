# fimpad/utils.py
from __future__ import annotations


def offset_to_tkindex(content: str, offset: int) -> str:
    if offset <= 0:
        return "1.0"
    lines = content.splitlines(keepends=True)
    acc = 0
    line_no = 1
    for line in lines:
        if acc + len(line) > offset:
            col = offset - acc
            return f"{line_no}.{col}"
        acc += len(line)
        line_no += 1
    return f"{line_no}.0"
