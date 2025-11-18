import pytest

from fimpad.parser import MARKER_REGEX


@pytest.mark.parametrize(
    "text",
    [
        "[[[0]]]",
        "[[[12]]]",
        "[[[ 123 ]]]",
        "[[[34 \"STOP\"]]]",
        "[[[56 \"STOP1\" \"STOP2\"]]]",
        "[[[78 'TAIL']]]",
        "[[[90 \"STOP\" 'TAIL']]]",
        "prefix [[[123]]] suffix",
        "[[[123!]]]",
        "[[[123 !]]]",
        "[[[456! \"STOP\"]]]",
        "[[[456 ! \"STOP\"]]]",
        "[[[789! 'TAIL']]]",
        "[[[20!'output:']]]",
        "[[[100\"Jane: \" ]]]",
    ],
)
def test_marker_regex_matches_numeric_markers(text):
    assert MARKER_REGEX.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "[[[system]]]",
        "[[[user]]]",
        "[[[assistant]]]",
        "[[[prefix]]]",
        "[[[suffix]]]",
        "[[[not-a-number]]]",
        "[[[123 words]]]",
        "[[[ 123 unquoted stop ]]]",
        "[[[  ]]]",
        "[[[123 \" 'mixed quotes without closing]]]",
        "[[[123 !!]]]",
        "[[[!123]]]",
    ],
)
def test_marker_regex_ignores_non_numeric_triple_brackets(text):
    assert MARKER_REGEX.search(text) is None
