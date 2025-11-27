import re
from collections.abc import Sequence


def _leading_whitespace(text: str) -> str:
    match = re.match(r"[ \t]*", text)
    return match.group(0) if match else ""


def _leading_whitespace_style(lines: Sequence[str]) -> str | None:
    prefixes = [_leading_whitespace(line) for line in lines]
    non_empty = [prefix for prefix in prefixes if prefix]
    if not non_empty:
        return None
    if all(set(prefix) <= {"\t"} for prefix in non_empty):
        return "tabs"
    if all(set(prefix) <= {" "} for prefix in non_empty):
        return "spaces"
    return "mixed"


def _indent_unit_for_lines(lines: Sequence[str], indent_size: int) -> str:
    if indent_size < 1:
        indent_size = 1
    elif indent_size > 8:
        indent_size = 8
    style = _leading_whitespace_style(lines)
    return "\t" if style == "tabs" else " " * indent_size


def _tabs_to_spaces(lines: Sequence[str], indent_size: int) -> list[str]:
    replacement = " " * max(1, min(indent_size, 8))
    converted: list[str] = []
    for line in lines:
        prefix = _leading_whitespace(line)
        converted.append(prefix.replace("\t", replacement) + line[len(prefix) :])
    return converted


def _spaces_to_tabs(lines: Sequence[str], indent_size: int) -> list[str]:
    tab_size = max(1, min(indent_size, 8))
    converted: list[str] = []
    for line in lines:
        prefix = _leading_whitespace(line)
        remainder = line[len(prefix) :]
        new_prefix_parts: list[str] = []
        space_run = 0
        for ch in prefix:
            if ch == " ":
                space_run += 1
                if space_run == tab_size:
                    new_prefix_parts.append("\t")
                    space_run = 0
            elif ch == "\t":
                if space_run:
                    new_prefix_parts.append(" " * space_run)
                    space_run = 0
                new_prefix_parts.append("\t")
        if space_run:
            new_prefix_parts.append(" " * space_run)
        converted.append("".join(new_prefix_parts) + remainder)
    return converted


def _indent_block(lines: Sequence[str], indent_size: int) -> list[str]:
    indent_unit = _indent_unit_for_lines(lines, indent_size)
    return [f"{indent_unit}{line}" for line in lines]


def _deindent_block(lines: Sequence[str], indent_size: int) -> list[str]:
    indent_unit = _indent_unit_for_lines(lines, indent_size)
    result: list[str] = []
    for line in lines:
        if indent_unit == "\t":
            if line.startswith("\t"):
                result.append(line[1:])
            else:
                result.append(line)
        else:
            space_count = len(line) - len(line.lstrip(" "))
            spaces_to_remove = min(space_count, len(indent_unit))
            result.append(line[spaces_to_remove:])
    return result


def _prepend_to_lines(lines: Sequence[str], prefix: str) -> list[str]:
    if not prefix:
        return list(lines)
    return [f"{prefix}{line}" for line in lines]


def _delete_leading_chars(lines: Sequence[str], count: int) -> list[str]:
    if count < 1:
        return list(lines)
    amount = min(count, 8)
    return [line[amount:] if len(line) > amount else "" for line in lines]
