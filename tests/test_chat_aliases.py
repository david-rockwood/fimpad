from fimpad.app import FIMPad
from fimpad.config import DEFAULTS


def make_app():
    app = FIMPad.__new__(FIMPad)
    app.cfg = DEFAULTS.copy()
    return app


def test_chat_tag_names_include_star_variants():
    app = make_app()
    names = app._chat_tag_names()
    assert "system*" in names
    assert "s*" in names
    assert "user*" in names


def test_contains_chat_tags_alias():
    app = make_app()
    assert app._contains_chat_tags("[[[s]]]")
    assert app._contains_chat_tags("[[[/s]]]")
    assert app._contains_chat_tags("[[[/u]]]")
    assert app._contains_chat_tags("[[[/a]]]")


def test_parse_chat_alias_normalizes_roles():
    app = make_app()
    content = "[[[s]]]System msg[[[/s]]][[[u]]]Hi[[[/u]]][[[a]]]Ack[[[/a]]]"
    messages = app._parse_chat_messages(content)
    assert messages == [
        {"role": "system", "content": "System msg"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Ack"},
    ]


def test_parse_chat_allows_starred_closer_in_non_star_mode():
    app = make_app()
    content = "[[[user]]]Hello[[[/user*]]]"
    messages = app._parse_chat_messages(content)
    assert messages == [{"role": "user", "content": "Hello"}]


def test_star_chat_block_detection():
    app = make_app()
    assert app._is_star_chat_block("[[[system*]]]Body")
    assert not app._is_star_chat_block("[[[system]]]Body")


def test_parse_chat_star_mode_treats_unstarred_tags_as_text():
    app = make_app()
    content = "[[[system*]]]First [[[u]]] block[[[/system*]]][[[user*]]]Second[[[/user*]]]"
    messages = app._parse_chat_messages(content, star_mode=True)
    assert messages == [
        {"role": "system", "content": "First [[[u]]] block"},
        {"role": "user", "content": "Second"},
    ]


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

