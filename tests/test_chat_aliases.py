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
    assert app._contains_chat_tags("[[[system1]]]")


def test_parse_chat_alias_normalizes_roles():
    app = make_app()
    content = "[[[s]]]System msg[[[/s]]][[[u]]]Hi[[[/u]]][[[a]]]Ack[[[/a]]]"
    messages = app._parse_chat_messages(content)
    assert messages == [
        {"role": "system", "content": "System msg"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Ack"},
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


def test_locate_chat_block_with_numbered_system_tag():
    app = make_app()
    content = "Intro\n[[[system1]]]\nExample\n[[[/system1]]]\nTail"
    cursor_offset = content.index("[[[system1]]]") + 2
    block = app._locate_chat_block(content, cursor_offset)
    assert block == (content.index("[[[system1]]]"), len(content))


def test_nested_chat_tags_treated_as_literal():
    app = make_app()
    content = (
        "[[[system]]]"
        "Explain [[[user]]] and [[[/user]]] placeholders."
        "[[[/system]]]"
        "[[[user]]]"
        "Please include [[[N]]] inside this response."
        "[[[/user]]]"
    )

    messages = app._parse_chat_messages(content)

    assert messages == [
        {
            "role": "system",
            "content": "Explain [[[user]]] and [[[/user]]] placeholders.",
        },
        {
            "role": "user",
            "content": "Please include [[[N]]] inside this response.",
        },
    ]


def test_numbered_system_tag_protects_literal_chat_tags():
    app = make_app()
    content = (
        "[[[system1]]]"
        "[[[s]]]\n[[[/s]]]\n[[[/u]]]\n[[[/a]]]\nAssist.\n[[[/s]]]"
        "[[[/system1]]]"
        "[[[user]]]Hi![[[/user]]]"
    )

    messages = app._parse_chat_messages(content)

    assert messages == [
        {
            "role": "system",
            "content": "[[[s]]]\n[[[/s]]]\n[[[/u]]]\n[[[/a]]]\nAssist.\n[[[/s]]]",
        },
        {"role": "user", "content": "Hi!"},
    ]

