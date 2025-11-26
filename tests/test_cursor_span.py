import pytest

from fimpad.parser import cursor_within_span


@pytest.mark.parametrize(
    "start,end,cursor_offset,expected",
    [
        (0, 9, 0, False),
        (0, 9, 4, True),
        (0, 9, 9, True),
        (0, 9, 10, False),
        (10, 20, 9, False),
        (10, 20, 10, False),
        (10, 20, 15, True),
        (10, 20, 20, True),
        (10, 20, 21, False),
    ],
)
def test_cursor_within_span(start, end, cursor_offset, expected):
    assert cursor_within_span(start, end, cursor_offset) is expected
