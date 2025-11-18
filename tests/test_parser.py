from fimpad.parser import (
    FIMRequest,
    TagToken,
    TextToken,
    parse_fim_request,
    parse_triple_tokens,
)


def test_parse_tokens_marker_and_regions():
    content = "[[[prefix]]]foo[[[42 ! \"stop\"]]]bar[[[suffix]]]"
    tokens = list(parse_triple_tokens(content))

    tag_tokens = [t for t in tokens if isinstance(t, TagToken)]
    assert [t.kind for t in tag_tokens] == ["prefix", "marker", "suffix"]

    marker_token = next(t for t in tag_tokens if t.kind == "marker")
    assert marker_token.body.startswith("42")

    texts = [t.text for t in tokens if isinstance(t, TextToken)]
    assert texts == ["foo", "bar"]


def test_parse_tokens_handles_adjacent_tags():
    content = "[[[prefix]]][[[10]]][[[suffix]]]"
    tokens = [t for t in parse_triple_tokens(content) if isinstance(t, TagToken)]

    assert [t.kind for t in tokens] == ["prefix", "marker", "suffix"]
    assert tokens[0].end == tokens[1].start
    assert tokens[1].end == tokens[2].start


def test_unknown_tags_are_classified():
    content = "before[[[custom]]]]after"
    tokens = [t for t in parse_triple_tokens(content) if isinstance(t, TagToken)]

    assert len(tokens) == 1
    assert tokens[0].kind == "unknown"
    assert tokens[0].name == "custom"


def test_parse_fim_request_finds_marker_and_regions():
    content = "[[[prefix]]]foo[[[12 ! \"stop\" 'tail']]]bar[[[suffix]]]"
    cursor_offset = content.index("12") + 1

    fim_request = parse_fim_request(content, cursor_offset, default_n=5)

    assert isinstance(fim_request, FIMRequest)
    assert fim_request.marker.body.startswith("12")
    assert fim_request.prefix_token is not None
    assert fim_request.suffix_token is not None
    assert fim_request.before_region == "foo"
    assert fim_request.after_region == "bar"
    assert fim_request.stops_before == ["stop"]
    assert fim_request.stops_after == ["tail"]
    assert fim_request.keep_tags is True
    assert fim_request.max_tokens == 12


def test_parse_fim_request_respects_default_and_bounds():
    content = "[[[99999]]]body"
    cursor_offset = content.index("99999")

    fim_request = parse_fim_request(content, cursor_offset, default_n=50)

    assert fim_request is not None
    assert fim_request.max_tokens == 4096
    assert fim_request.use_completion is False
    assert fim_request.safe_suffix == "body"


def test_parse_fim_request_requires_cursor_inside_marker():
    content = "[[[prefix]]]text[[[10]]]after"
    outside_offset = content.index("text")

    assert parse_fim_request(content, outside_offset, default_n=5) is None
