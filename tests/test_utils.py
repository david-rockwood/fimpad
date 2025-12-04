import pytest

from fimpad.utils import offset_to_tkindex


@pytest.mark.parametrize(
    "content, offset, expected",
    [
        ("A😊B", 2, "1.3"),
        ("A😊B", 3, "1.4"),
        ("A😊B\nC", 4, "2.0"),
        ("", 0, "1.0"),
    ],
)
def test_offset_to_tkindex_counts_utf16_units(content, offset, expected):
    assert offset_to_tkindex(content, offset) == expected
