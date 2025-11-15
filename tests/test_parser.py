from fimpad.parser import ChatBlock, TagToken, TextToken, parse_chat_block, parse_triple_tokens


def test_parse_tokens_marker_and_regions():
    content = "[[[prefix]]]foo[[[42 ! \"stop\"]]]bar[[[suffix]]]"
    tokens = list(parse_triple_tokens(content))

    tag_tokens = [t for t in tokens if isinstance(t, TagToken)]
    assert [t.kind for t in tag_tokens] == ["prefix", "marker", "suffix"]

    marker_token = next(t for t in tag_tokens if t.kind == "marker")
    assert marker_token.body.startswith("42")

    texts = [t.text for t in tokens if isinstance(t, TextToken)]
    assert texts == ["foo", "bar"]


def test_parse_tokens_resolves_role_aliases():
    content = "[[[system]]]hi[[[/system]]]"
    role_aliases = {
        "system": "system",
        "/system": "system",
        "s": "system",
        "/s": "system",
    }

    tokens = [
        t
        for t in parse_triple_tokens(content, role_aliases=role_aliases)
        if isinstance(t, TagToken)
    ]

    assert tokens[0].kind == "chat"
    assert tokens[0].role == "system"
    assert tokens[0].is_close is False

    assert tokens[-1].is_close is True


def test_parse_tokens_handles_adjacent_tags():
    content = "[[[prefix]]][[[10]]][[[suffix]]]"
    tokens = [t for t in parse_triple_tokens(content) if isinstance(t, TagToken)]

    assert [t.kind for t in tokens] == ["prefix", "marker", "suffix"]
    assert tokens[0].end == tokens[1].start
    assert tokens[1].end == tokens[2].start


def test_parse_chat_block_handles_nested_tags():
    role_aliases = {
        "system": "system",
        "/system": "system",
        "user": "user",
        "/user": "user",
        "assistant": "assistant",
        "/assistant": "assistant",
        "s": "system",
        "/s": "system",
        "u": "user",
        "/u": "user",
    }

    content = (
        "[[[system]]]System text [[[user]]]should stay[[[/user]]]!\n"
        "[[[u]]]User sees [[[assistant]]] code[[[/assistant]]] here[[[/u]]]"
        "[[[/system]]]"
    )

    block = parse_chat_block(content, role_aliases=role_aliases)

    assert isinstance(block, ChatBlock)
    assert list(block.messages) == [
        ("system", "System text "),
        ("user", "should stay"),
        ("system", "!\n"),
        ("user", "User sees "),
        ("assistant", " code"),
        ("user", " here"),
        ("system", ""),
    ]


def test_parse_tokens_resolves_star_aliases():
    role_aliases = {
        "system": "system",
        "user": "user",
    }

    content = "[[[system*]]]One[[[/system*]]][[[user*]]]Two[[[/user*]]]"

    tokens = [
        token
        for token in parse_triple_tokens(content, role_aliases=role_aliases)
        if isinstance(token, TagToken)
    ]

    assert [t.role for t in tokens if not t.is_close] == ["system", "user"]
    assert [t.role for t in tokens if t.is_close] == ["system", "user"]
    assert tokens[0].name == "system*"
    assert tokens[-1].name == "user*"


def test_parse_chat_block_star_mode_nested_tags():
    role_aliases = {
        "system": "system",
        "/system": "system",
        "user": "user",
        "/user": "user",
        "assistant": "assistant",
        "/assistant": "assistant",
    }

    content = (
        "[[[system*]]]System [[[user*]]]nest[[[/user*]]] text[[[/system*]]]"
        "[[[assistant*]]]Reply[[[/assistant*]]]"
    )

    block = parse_chat_block(content, role_aliases=role_aliases)

    assert list(block.messages) == [
        ("system", "System "),
        ("user", "nest"),
        ("system", " text"),
        ("assistant", "Reply"),
    ]
