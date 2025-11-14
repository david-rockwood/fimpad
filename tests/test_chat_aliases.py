from fimpad.app import FIMPad
from fimpad.config import DEFAULTS


def make_app():
    app = FIMPad.__new__(FIMPad)
    app.cfg = DEFAULTS.copy()
    return app


def test_contains_chat_tags_alias():
    app = make_app()
    assert app._contains_chat_tags("[[[s]]]")
    assert app._contains_chat_tags("[[[/s]]]")
    assert app._contains_chat_tags("[[[/u]]]")
    assert app._contains_chat_tags("[[[/a]]]")


def test_parse_chat_alias_normalizes_roles():
    app = make_app()
    content = "[[[s]]]System msg[[[/s]]][[[u]]]Hi[[[/u]]][[[a]]]Ack[[[/a]]]"
    block = app._parse_chat_messages(content)
    assert list(block.messages) == [
        {"role": "system", "content": "System msg"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Ack"},
    ]
    assert block.star_mode is False


def test_star_mode_treats_inner_tags_as_text():
    app = make_app()
    content = "[[[system*]]]Inner [[[user]]]tag[[[/user]]] text[[[/system*]]]"
    block = app._parse_chat_messages(content)
    assert block.star_mode is True
    assert list(block.messages) == [
        {"role": "system", "content": "Inner [[[user]]]tag[[[/user]]] text"}
    ]


def test_star_mode_placeholder_uses_star_tags():
    app = make_app()
    content = "[[[system*]]]\nAssist.\n[[[/system*]]]"
    block = app._parse_chat_messages(content)

    replacement, normalized_messages, *_ = app._render_chat_block(block)

    assert normalized_messages == [{"role": "system", "content": "Assist."}]
    assert "[[[assistant*]]]" in replacement
    assert replacement.rstrip().endswith("[[[/assistant*]]]")


def test_star_mode_normalization_preserves_inner_tags():
    app = make_app()
    content = (
        "[[[system*]]]\n"
        "Outer star message with [[[user]]]plain[[[/user]]] tags.\n"
        "[[[/system*]]]"
    )

    block = app._parse_chat_messages(content)
    rendered, *_ = app._render_chat_block(block)

    assert "[[[system*]]]" in rendered
    assert "[[[user]]]plain[[[/user]]]" in rendered
    assert "[[[user*]]]plain" not in rendered


def test_close_tag_aliases_are_available():
    app = make_app()
    aliases = app._chat_role_aliases()
    assert aliases["/s"] == "system"
    assert aliases["/u"] == "user"
    assert aliases["/a"] == "assistant"


def test_locate_chat_block_with_alias():
    app = make_app()
    content = "Intro\n[[[s]]]\nBody\n[[[/s]]]\nTail"
    cursor_offset = content.index("[[[s]]]") + 2
    block = app._locate_chat_block(content, cursor_offset)
    assert block == (content.index("[[[s]]]"), len(content))


def test_locate_chat_block_star_mode_prefers_star_system():
    app = make_app()
    content = (
        "[[[system]]]Plain system[[[/system]]]"
        "\n\n[[[system*]]]\n[[[user*]]]Hello[[[/user*]]]\n[[[/system*]]]"
    )
    cursor_offset = content.index("Hello") + 1

    block = app._locate_chat_block(content, cursor_offset)

    star_start = content.index("[[[system*]]]")
    assert block == (star_start, len(content))


def test_chat_user_followup_block_respects_star_mode():
    app = make_app()

    star_block, star_offset = app._chat_user_followup_block(True)
    assert "[[[user*]]]" in star_block
    assert star_block.rstrip().endswith("[[[/user*]]]")
    assert star_offset == len("\n\n[[[user*]]]\n")

    plain_block, plain_offset = app._chat_user_followup_block(False)
    assert "[[[user*]]]" not in plain_block
    assert plain_block.rstrip().endswith("[[[/user]]]")
    assert plain_offset == len("\n\n[[[user]]]\n")

