import pytest

from fimpad.bol_utils import (
    _deindent_block,
    _delete_leading_chars,
    _indent_block,
    _indent_unit_for_lines,
    _leading_whitespace_style,
    _spaces_to_tabs,
    _tabs_to_spaces,
)


@pytest.mark.parametrize(
    "lines,expected",
    [
        (["\tfoo", "\tbar"], "tabs"),
        (["  foo", " bar"], "spaces"),
        (["foo", "bar"], None),
        (["\tfoo", "  bar"], "mixed"),
    ],
)
def test_leading_whitespace_style(lines, expected):
    assert _leading_whitespace_style(lines) == expected


def test_indent_unit_prefers_tabs_only_when_all_tabs():
    assert _indent_unit_for_lines(["\tfoo", "\tbar"], 4) == "\t"
    assert _indent_unit_for_lines(["foo", "bar"], 2) == "  "
    assert _indent_unit_for_lines(["\tfoo", " bar"], 2) == "  "


def test_tabs_and_spaces_conversion():
    assert _tabs_to_spaces(["\tfoo", "\t\tbar"], 2) == ["  foo", "    bar"]
    assert _spaces_to_tabs(["    foo", "        bar"], 4) == ["\tfoo", "\t\tbar"]
    assert _spaces_to_tabs(["   foo"], 4) == ["   foo"]


def test_indent_and_deindent_respects_block_style():
    lines = ["alpha", " beta"]
    indented = _indent_block(lines, 4)
    assert indented == ["    alpha", "     beta"]
    assert _deindent_block(indented, 4) == lines

    tab_lines = ["\talpha", "\tbeta"]
    tab_indented = _indent_block(tab_lines, 4)
    assert tab_indented == ["\t\talpha", "\t\tbeta"]
    assert _deindent_block(tab_indented, 4) == tab_lines


def test_delete_leading_chars_truncates_safely():
    assert _delete_leading_chars(["abc", "", "ab"], 3) == ["", "", ""]
    assert _delete_leading_chars(["abcdef"], 2) == ["cdef"]
