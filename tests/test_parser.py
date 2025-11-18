from fimpad.parser import TagToken, TextToken, parse_triple_tokens


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
