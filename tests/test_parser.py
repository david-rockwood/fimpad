import pytest

from fimpad.parser import (
    CommentTag,
    FIMFunction,
    FIMRequest,
    FIMTag,
    PrefixSuffixTag,
    SequenceTag,
    TagParseError,
    TagToken,
    TextToken,
    cursor_within_span,
    parse_fim_request,
    parse_triple_tokens,
)


def _collect_tags(content: str):
    return [t for t in parse_triple_tokens(content) if isinstance(t, TagToken)]


def stitch_tokens(tokens):
    parts = []
    for token in tokens:
        if isinstance(token, TextToken):
            parts.append(token.text)
        else:
            parts.append(token.raw)
    return "".join(parts)


def test_parse_triple_tokens_classifies_tag_types_and_reconstructs():
    content = (
        "A [[[5 \"alpha\"]]] B [[[\"one\" 'two']]] C [[[prefix]]] "
        "D [[[suffix!]]] E [[[(note about things) after]]]" """ F"""
    )
    tokens = list(parse_triple_tokens(content))

    assert stitch_tokens(tokens) == content

    tag_tokens = _collect_tags(content)
    kinds = [t.kind for t in tag_tokens]
    assert kinds == ["fim", "sequence", "prefix", "suffix", "comment"]

    prefix = tag_tokens[2]
    assert isinstance(prefix.tag, PrefixSuffixTag)
    assert prefix.tag.hardness == "soft" and not prefix.tag.is_close

    suffix = tag_tokens[3]
    assert isinstance(suffix.tag, PrefixSuffixTag)
    assert suffix.tag.hardness == "hard"

    comment = tag_tokens[4]
    assert isinstance(comment.tag, CommentTag)
    assert comment.tag.body == "note about things"
    assert comment.tag.position == "after"


def test_fim_tag_functions_capture_phases_and_order():
    content = "[[[12! \"alpha\" 'omega' stop(\"beta\") after:stop('gamma') name(foo)]]]"
    fim_token = _collect_tags(content)[0]

    assert fim_token.kind == "fim"
    assert isinstance(fim_token.tag, FIMTag)
    fim_tag = fim_token.tag
    assert fim_tag.max_tokens == 12

    functions = list(fim_tag.functions)
    assert [fn.name for fn in functions] == [
        "keep_tags",
        "stop",
        "stop",
        "stop",
        "stop",
        "name",
    ]

    assert functions[1].phase == "before" and functions[1].args == ("alpha",)
    assert functions[2].phase == "after" and functions[2].args == ("omega",)
    assert functions[3].phase == "init" and functions[3].args == ("beta",)
    assert functions[4].phase == "after" and functions[4].args == ("gamma",)
    assert functions[5].args == ("foo",)


def test_sequence_tag_parses_strings_with_escapes():
    content = '[[["first step" "line\\n2"]]]'
    token = _collect_tags(content)[0]
    assert token.kind == "sequence"
    assert isinstance(token.tag, SequenceTag)
    assert token.tag.names == ("first step", "line\n2")


def test_duplicate_names_raise():
    content = "[[[1 name(foo)]]] [[[2 name(foo)]]]"
    with pytest.raises(TagParseError):
        list(parse_triple_tokens(content))


def test_unknown_function_raises():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[1 unknown()]]]]"))


def test_parse_fim_request_uses_new_ast(monkeypatch):
    content = "[[[prefix]]] AAA [[[5! \"alpha\" 'omega']]] BBB [[[suffix hard]]]"
    tokens = _collect_tags(content)
    marker = tokens[1]
    cursor_offset = marker.start + 2

    fim_request = parse_fim_request(content, cursor_offset, default_n=50)
    assert isinstance(fim_request, FIMRequest)
    assert fim_request.prefix_token == tokens[0]
    assert fim_request.suffix_token == tokens[2]
    assert fim_request.before_region == " AAA "
    assert fim_request.after_region == " BBB "
    assert fim_request.max_tokens == 5
    assert fim_request.keep_tags is True
    assert fim_request.stop_patterns == ["alpha"]
    assert fim_request.chop_patterns == ["omega"]
    assert fim_request.safe_suffix == " BBB "


def test_parse_fim_request_strips_comments_and_collects_overrides():
    content = "[[[prefix soft]]] Hello [[[(note) before]]] [[[3 stop(\"zip\") chop('zap') top_p(0.4) append('!')]]] [[[suffix]]]\n"
    tokens = _collect_tags(content)
    marker = tokens[2]
    fim_request = parse_fim_request(content, marker.start + 1)

    assert fim_request.before_region.strip() == "Hello"
    assert fim_request.after_region.strip() == ""
    assert fim_request.stop_patterns == ["zip"]
    assert fim_request.chop_patterns == ["zap"]
    assert fim_request.config_overrides["top_p"] == 0.4
    assert [fn.name for fn in fim_request.post_functions] == ["append"]


def test_cursor_within_span_accepts_immediate_after():
    start, end = 5, 10
    assert cursor_within_span(start, end, end)
    assert not cursor_within_span(start, end, end + 1)
