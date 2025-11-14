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

