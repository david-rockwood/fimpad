import pytest

from fimpad.parser import (
    FIMRequest,
    TagToken,
    TextToken,
    cursor_within_span,
    parse_fim_request,
    parse_triple_tokens,
)


# Helpers --------------------------------------------------------------------


def _marker_tokens(content: str):
    return [
        t
        for t in parse_triple_tokens(content)
        if isinstance(t, TagToken) and t.kind == "marker"
    ]


def make_request_for_marker(
    content: str, marker_index: int = 0, *, cursor_at: str = "inside", default_n: int = 123
) -> FIMRequest | None:
    markers = _marker_tokens(content)
    marker = markers[marker_index]
    if cursor_at == "inside":
        cursor_offset = marker.start + 1
    elif cursor_at == "after":
        cursor_offset = marker.end
    else:
        raise ValueError("cursor_at must be 'inside' or 'after'")
    return parse_fim_request(content, cursor_offset, default_n=default_n)


def stitch_tokens(tokens):
    parts = []
    for token in tokens:
        if isinstance(token, TextToken):
            parts.append(token.text)
        else:
            parts.append(token.raw)
    return "".join(parts)


# 1) BASIC TRIPLE-TOKENIZATION -----------------------------------------------

def test_parse_triple_tokens_without_tags():
    content = "just some plain text"
    tokens = list(parse_triple_tokens(content))

    assert tokens == [TextToken(start=0, end=len(content), text=content)]


def test_parse_triple_tokens_classifies_tags_and_spans_reconstruct():
    content = "A [[[10]]] B [[[prefix]]] C [[[suffix]]] D"
    tokens = list(parse_triple_tokens(content))

    # Reconstruction check
    assert stitch_tokens(tokens) == content

    tag_tokens = [t for t in tokens if isinstance(t, TagToken)]
    kinds = [t.kind for t in tag_tokens]
    assert kinds == ["marker", "prefix", "suffix"]

    marker = tag_tokens[0]
    assert marker.body == "10"
    assert marker.start < marker.end

    prefix = tag_tokens[1]
    suffix = tag_tokens[2]
    assert prefix.kind == "prefix" and prefix.name == "prefix" and not prefix.is_close
    assert suffix.kind == "suffix" and suffix.name == "suffix" and not suffix.is_close

    # Span sanity: text tokens should fill the gaps.
    text_spans = [(t.start, t.end) for t in tokens if isinstance(t, TextToken)]
    assert text_spans[0][0] == 0
    assert text_spans[-1][1] == len(content)


def test_parse_triple_tokens_handles_closing_tags():
    content = "X [[[prefix]]] Y [[[ /prefix ]]] Z [[[suffix]]] Q [[[ /suffix ]]]"
    tag_tokens = [t for t in parse_triple_tokens(content) if isinstance(t, TagToken)]

    kinds = [t.kind for t in tag_tokens]
    assert kinds == ["prefix", "prefix", "suffix", "suffix"]

    open_prefix, close_prefix, open_suffix, close_suffix = tag_tokens
    assert not open_prefix.is_close
    assert close_prefix.is_close
    assert close_suffix.is_close
    # Ensure parsing continues after a closing tag.
    assert open_suffix.kind == "suffix"


# 2) FINDING THE ACTIVE MARKER AROUND THE CARET ------------------------------

def test_parse_fim_request_cursor_inside_and_after_marker():
    content = "foo [[[10]]] bar"
    marker = _marker_tokens(content)[0]

    inside_request = parse_fim_request(content, marker.start + 1, default_n=123)
    after_request = parse_fim_request(content, marker.end, default_n=123)
    outside_request = parse_fim_request(content, 0, default_n=123)

    assert inside_request is not None and inside_request.marker == marker
    assert after_request is not None and after_request.marker == marker
    assert outside_request is None


@pytest.mark.parametrize(
    "cursor_fn",
    [lambda m: m.start + 1, lambda m: m.end],
)
def test_parse_fim_request_selects_correct_marker_with_multiple(cursor_fn):
    content = "A [[[10]]] B [[[20]]] C"
    markers = _marker_tokens(content)

    first_cursor = cursor_fn(markers[0])
    second_cursor = cursor_fn(markers[1])

    first_req = parse_fim_request(content, first_cursor, default_n=123)
    second_req = parse_fim_request(content, second_cursor, default_n=123)

    assert first_req is not None and first_req.marker == markers[0]
    assert second_req is not None and second_req.marker == markers[1]


# 3) PREFIX/SUFFIX SCOPING SEMANTICS ----------------------------------------

def test_fim_request_no_tags():
    # No prefix/suffix wrapping the marker
    content = "AAA [[[10]]] BBB"
    fim_request = make_request_for_marker(content)

    assert fim_request.prefix_token is None
    assert fim_request.suffix_token is None
    assert fim_request.before_region == "AAA "
    assert fim_request.after_region == " BBB"


def test_fim_request_single_prefix_above_marker():
    content = "[[[prefix]]] AAA [[[10]]] BBB"
    fim_request = make_request_for_marker(content)

    assert fim_request.prefix_token is not None
    assert fim_request.prefix_token.kind == "prefix"
    assert fim_request.suffix_token is None
    assert fim_request.before_region == " AAA "
    assert fim_request.after_region == " BBB"


def test_fim_request_single_suffix_below_marker():
    content = "AAA [[[10]]] BBB [[[suffix]]] CCC"
    fim_request = make_request_for_marker(content)

    assert fim_request.prefix_token is None
    assert fim_request.suffix_token is not None
    assert fim_request.before_region == "AAA "
    assert fim_request.after_region == " BBB "


def test_fim_request_prefix_and_suffix_wrapping_marker():
    content = "[[[prefix]]] AAA [[[10]]] BBB [[[suffix]]] CCC"
    fim_request = make_request_for_marker(content)

    assert fim_request.prefix_token is not None
    assert fim_request.suffix_token is not None
    assert fim_request.before_region == " AAA "
    assert fim_request.after_region == " BBB "


def test_fim_request_multiple_markers_share_prefix_suffix():
    content = "[[[prefix]]] A [[[10]]] B [[[20]]] C [[[suffix]]] D"

    first_req = make_request_for_marker(content, 0)
    second_req = make_request_for_marker(content, 1)

    assert first_req.prefix_token is not None and first_req.suffix_token is not None
    assert second_req.prefix_token is not None and second_req.suffix_token is not None

    assert first_req.before_region == " A "
    assert first_req.after_region == " B [[[20]]] C "

    # For the second marker, before_region starts after the same prefix
    assert second_req.before_region == " A [[[10]]] B "
    assert second_req.after_region == " C "


def test_fim_request_multiple_prefix_tags_closest_above_wins():
    content = "[[[prefix]]] A [[[10]]] B [[[prefix]]] C [[[20]]] D"

    first_req = make_request_for_marker(content, 0)
    second_req = make_request_for_marker(content, 1)

    assert first_req.prefix_token.start < second_req.prefix_token.start
    assert first_req.before_region == " A "
    assert second_req.before_region == " C "


def test_fim_request_multiple_suffix_tags_next_below_wins():
    content = "A [[[10]]] B [[[suffix]]] C [[[20]]] D [[[suffix]]] E"

    first_req = make_request_for_marker(content, 0)
    second_req = make_request_for_marker(content, 1)

    assert first_req.suffix_token.start < second_req.suffix_token.start
    assert first_req.after_region == " B "
    assert second_req.after_region == " D "


# 4) SAFE SUFFIX AND STOP SEQUENCES -----------------------------------------

def test_safe_suffix_strips_numeric_markers():
    content = "AAA [[[5]]] BBB [[[10]]] CCC"
    fim_request = make_request_for_marker(content, 0)

    assert "[[[10]]]" in fim_request.after_region
    assert "[[[10]]]" not in fim_request.safe_suffix


def test_max_tokens_explicit_and_default(monkeypatch):
    content = "AAA [[[7]]] BBB"
    explicit_req = make_request_for_marker(content, 0, default_n=123)
    assert explicit_req.max_tokens == 7

    # Simulate an empty marker body to ensure default_n fallback is honored.
    from fimpad import parser as parser_mod

    fake_marker = TagToken(start=0, end=3, raw="[[[]]]", body="", kind="marker")

    def fake_tokens(_):
        return [fake_marker]

    monkeypatch.setattr(parser_mod, "parse_triple_tokens", fake_tokens)
    fallback_req = parse_fim_request("", cursor_offset=1, default_n=123)
    assert fallback_req is not None
    assert fallback_req.max_tokens == 123


def test_stop_sequences_split_into_before_and_after():
    content = "AAA [[[5 \"alpha\" 'omega']]] BBB"
    fim_request = make_request_for_marker(content, 0)

    assert fim_request.stops_before == ["alpha"]
    assert fim_request.stops_after == ["omega"]


# 5) cursor_within_span adjacency check -------------------------------------

def test_cursor_within_span_accepts_immediate_after():
    start, end = 5, 10
    # Position right after the end should still be treated as within span.
    assert cursor_within_span(start, end, end)
    assert not cursor_within_span(start, end, end + 1)
