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
        "A [[[5; stop(\"alpha\"); name(one)]]] "
        "B [[[2; name(two)]]] [[[\"one\" 'two']]] "
        "C [[[prefix]]] D [[[suffix hard]]] E [[[(note about things) after]]]" """ F"""
    )
    tokens = list(parse_triple_tokens(content))

    assert stitch_tokens(tokens) == content

    tag_tokens = _collect_tags(content)
    kinds = [t.kind for t in tag_tokens]
    assert kinds == ["fim", "fim", "sequence", "prefix", "suffix", "comment"]

    prefix = tag_tokens[3]
    assert isinstance(prefix.tag, PrefixSuffixTag)
    assert prefix.tag.hardness == "soft" and not prefix.tag.is_close

    suffix = tag_tokens[4]
    assert isinstance(suffix.tag, PrefixSuffixTag)
    assert suffix.tag.hardness == "hard"

    comment = tag_tokens[5]
    assert isinstance(comment.tag, CommentTag)
    assert comment.tag.body == "note about things"
    assert comment.tag.position == "after"


def test_fim_tag_functions_capture_phases_and_order_with_semicolons_and_multiline():
    content = (
        "[[[12; keep_tags();\n"
        '    before:stop("alpha"); after:stop(\'omega\');\n'
        '    stop("beta"); after:stop(\'ga\\\'mma\');\n'
        '    chop("line\\n3"); name(foo)\n'
        "]]]\n"
    )
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
        "chop",
        "name",
    ]

    assert functions[1].phase == "before" and functions[1].args == ("alpha",)
    assert functions[2].phase == "after" and functions[2].args == ("omega",)
    assert functions[3].phase == "init" and functions[3].args == ("beta",)
    assert functions[4].phase == "after" and functions[4].args == ("ga'mma",)
    assert functions[5].phase == "init" and functions[5].args == ("line\n3",)
    assert functions[6].args == ("foo",)


def test_sequence_tag_parses_strings_with_escapes():
    content = (
        "[[[1; name(first)]]]\n[[[2; name('line\\n2')]]]\n[[[\"first\" \"line\\n2\"]]]"
    )
    tokens = _collect_tags(content)
    token = tokens[-1]
    assert token.kind == "sequence"
    assert isinstance(token.tag, SequenceTag)
    assert token.tag.names == ("first", "line\n2")


def test_sequence_tag_validates_named_targets_and_duplicates():
    content = """
    [[[2; name(first)]]]
    [[[3; name(second)]]]
    [[["first" "second"]]]
    """
    tokens = list(parse_triple_tokens(content))
    names = [
        fn.args[0]
        for t in tokens
        if isinstance(t, TagToken)
        and isinstance(t.tag, FIMTag)
        for fn in t.tag.functions
        if fn.name == "name"
    ]
    assert names == ["first", "second"]


def test_sequence_tag_missing_name_raises():
    content = """
    [[[1; name(alpha)]]]
    [[["alpha" "beta"]]]
    """
    with pytest.raises(TagParseError):
        list(parse_triple_tokens(content))


def test_duplicate_names_raise():
    content = "[[[1; name(foo)]]] [[[2; name(foo)]]]"
    with pytest.raises(TagParseError):
        list(parse_triple_tokens(content))


def test_bare_fim_tag_without_functions():
    tokens = _collect_tags("Before [[[7]]] After")
    fim_token = tokens[0]

    assert fim_token.kind == "fim"
    assert isinstance(fim_token.tag, FIMTag)
    assert fim_token.tag.max_tokens == 7
    assert fim_token.tag.functions == ()


def test_multifunction_tag_collects_stops_chops_and_post_actions():
    content = (
        "AAA [[[4; stop(\"one\"); chop('two'); append('!'); append_nl('more'); "
        "after:stop('tail')]]] BBB"
    )
    marker = _collect_tags(content)[0]

    fim_request = parse_fim_request(content, marker.start + 1, default_n=50)
    assert fim_request is not None
    assert fim_request.max_tokens == 4
    assert fim_request.stop_patterns == ["one"]
    assert fim_request.chop_patterns == ["two", "tail"]
    assert [fn.name for fn in fim_request.post_functions] == [
        "append",
        "append_nl",
    ]


def test_unknown_function_raises():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[1; unknown()]]]]"))


def test_bang_after_fim_count_rejected():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[50!]]]"))


def test_missing_semicolon_after_fim_count_rejected():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[5 stop('cut')]]]"))


def test_string_literal_outside_function_rejected():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[5; \"alpha\"]]]"))


def test_string_args_allow_internal_whitespace():
    fim_token = _collect_tags("[[[50;stop(\" forth\")]]]")[0]

    assert isinstance(fim_token.tag, FIMTag)
    assert fim_token.tag.functions[0].args == (" forth",)


def test_implicit_string_stop_rejected():
    with pytest.raises(TagParseError):
        list(parse_triple_tokens("[[[100'User: ']]]"))


def test_new_dsl_accepts_supported_functions_and_phases():
    content = (
        "[[[42; keep(); keep_tags(); stop(\"alpha\"); after:tail('done'); "
        "post:append(\"tail\"); append_nl('more'); temperature(0.4); top_p(0.9); "
        "name(sample)]]]"
    )
    fim_token = _collect_tags(content)[0]

    assert fim_token.kind == "fim"
    assert isinstance(fim_token.tag, FIMTag)

    function_names = [fn.name for fn in fim_token.tag.functions]
    assert function_names == [
        "keep",
        "keep_tags",
        "stop",
        "tail",
        "append",
        "append_nl",
        "temperature",
        "top_p",
        "name",
    ]

    functions = fim_token.tag.functions
    assert functions[0].phase == "meta"
    assert functions[1].phase == "meta"
    assert functions[2].args == ("alpha",) and functions[2].phase == "init"
    assert functions[3].args == ("done",) and functions[3].phase == "after"
    assert functions[4].args == ("tail",) and functions[4].phase == "post"
    assert functions[5].args == ("more",) and functions[5].phase == "post"
    assert functions[6].args == ("0.4",) and functions[6].phase == "init"
    assert functions[7].args == ("0.9",) and functions[7].phase == "init"
    assert functions[8].args == ("sample",) and functions[8].phase == "meta"


def test_parse_fim_request_uses_new_ast(monkeypatch):
    content = (
        "[[[prefix]]] AAA [[[5; keep_tags(); stop(\"alpha\"); chop('omega')]]] "
        "BBB [[[suffix hard]]]"
    )
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


def test_parse_fim_request_excludes_comments_and_honors_prefix_suffix_hardness():
    content = (
        "[[[prefix soft]]]A [[[(note) before]]] [[[2; stop('cut')]]]\n"
        "B [[[(not used) after]]] [[[suffix hard]]] tail"
    )
    tokens = _collect_tags(content)
    marker = tokens[2]
    fim_request = parse_fim_request(content, marker.start + 1)

    assert fim_request.before_region.strip() == "A"
    assert fim_request.after_region.startswith("\nB ")
    assert fim_request.safe_suffix.startswith("\nB ")

    prefix_token = tokens[0]
    suffix_token = tokens[-1]
    assert isinstance(prefix_token.tag, PrefixSuffixTag)
    assert prefix_token.tag.hardness == "soft"
    assert isinstance(suffix_token.tag, PrefixSuffixTag)
    assert suffix_token.tag.hardness == "hard"


def test_prefix_suffix_comment_and_sequence_tags_still_parse():
    content = (
        "[[[prefix hard]]] [[[1; name(foo)]]] Body [[[suffix soft]]]\n"
        "[[[(note) before]]] [[[\"foo\"]]]"
    )
    tokens = list(parse_triple_tokens(content))

    kinds = [t.kind for t in tokens if isinstance(t, TagToken)]
    assert kinds == ["prefix", "fim", "suffix", "comment", "sequence"]

    prefix_token, fim_token, suffix_token, comment_token, sequence_token = [
        t for t in tokens if isinstance(t, TagToken)
    ]

    assert isinstance(prefix_token.tag, PrefixSuffixTag)
    assert prefix_token.tag.hardness == "hard"
    assert isinstance(suffix_token.tag, PrefixSuffixTag)
    assert suffix_token.tag.hardness == "soft"

    assert isinstance(comment_token.tag, CommentTag)
    assert comment_token.tag.body == "note"
    assert comment_token.tag.position == "before"

    assert isinstance(sequence_token.tag, SequenceTag)
    assert sequence_token.tag.names == ("foo",)


def test_parse_fim_request_strips_comments_and_collects_overrides():
    content = (
        "[[[prefix soft]]] Hello [[[(note) before]]] "
        "[[[3; stop(\"zip\"); chop('zap'); top_p(0.4); append('!')]]] [[[suffix]]]\n"
    )
    tokens = _collect_tags(content)
    marker = tokens[2]
    fim_request = parse_fim_request(content, marker.start + 1)

    assert fim_request.before_region.strip() == "Hello"
    assert fim_request.after_region.strip() == ""
    assert fim_request.stop_patterns == ["zip"]
    assert fim_request.chop_patterns == ["zap"]
    assert fim_request.config_overrides["top_p"] == 0.4
    assert [fn.name for fn in fim_request.post_functions] == ["append"]


def test_stop_and_chop_tie_breaking_prefers_chop():
    content = "[[[2; stop(\"shared\"); chop('shared'); after:stop('later')]]]"
    token = _collect_tags(content)[0]
    fim_request = parse_fim_request(content, token.start + 1)

    assert fim_request.stop_patterns == []
    assert fim_request.chop_patterns == ["shared", "later"]


def test_cursor_within_span_accepts_immediate_after():
    start, end = 5, 10
    assert cursor_within_span(start, end, end)
    assert not cursor_within_span(start, end, end + 1)
