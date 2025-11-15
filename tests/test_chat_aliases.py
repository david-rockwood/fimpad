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
        ("system", "System msg"),
        ("user", "Hi"),
        ("assistant", "Ack"),
    ]


def test_nested_chat_tags_split_messages():
    app = make_app()
    content = "[[[system]]]Inner [[[user]]]tag[[[/user]]] text[[[/system]]]"
    block = app._parse_chat_messages(content)
    assert list(block.messages) == [
        ("system", "Inner "),
        ("user", "tag"),
        ("system", " text"),
    ]


def test_render_chat_block_uses_plain_tags():
    app = make_app()
    content = "[[[system]]]\nAssist.\n[[[/system]]]"
    block = app._parse_chat_messages(content)

    replacement, normalized_messages, *_ = app._render_chat_block(block)

    assert normalized_messages == [{"role": "system", "content": "Assist."}]
    assert "[[[assistant]]]" in replacement
    assert replacement.rstrip().endswith("[[[/assistant]]]")


def test_render_chat_block_preserves_inner_tags():
    app = make_app()
    content = (
        "[[[system]]]\n"
        "Outer message with [[[user]]]plain[[[/user]]] tags.\n"
        "[[[/system]]]"
    )

    block = app._parse_chat_messages(content)
    rendered, *_ = app._render_chat_block(block)

    assert "[[[system]]]" in rendered
    assert "[[[user]]]\nplain\n[[[/user]]]" in rendered
    assert "[[[user*]]]plain" not in rendered


def test_close_tag_aliases_are_available():
    app = make_app()
    aliases = app._chat_role_aliases()
    assert aliases["/s"] == "system"
    assert aliases["/u"] == "user"
    assert aliases["/a"] == "assistant"


def test_locate_chat_block_prefers_later_system():
    app = make_app()
    content = (
        "[[[system]]]Plain system[[[/system]]]"
        "\n\n[[[system]]]\n[[[user]]]Hello[[[/user]]]\n[[[/system]]]"
    )
    cursor_offset = content.index("Hello") + 1

    block = app._locate_chat_block(content, cursor_offset)

    second_start = content.index("[[[system]]]\n[[[user]]]")
    assert block == (second_start, len(content))


def test_chat_user_followup_block_inserts_plain_tags():
    app = make_app()

    block_text, cursor_offset = app._chat_user_followup_block()
    assert "[[[user]]]" in block_text
    assert block_text.rstrip().endswith("[[[/user]]]")
    assert cursor_offset == len("\n\n[[[user]]]\n")


def test_chat_config_star_suffixes_are_normalized():
    app = make_app()
    app.cfg["chat_system"] = "System*"
    app.cfg["chat_user"] = "User*"
    app.cfg["chat_assistant"] = "Assistant*"

    content = "[[[system]]]Hello[[[/system]]]"
    block = app._parse_chat_messages(content)

    assert list(block.messages) == [("system", "Hello")]

    rendered, normalized_messages, *_ = app._render_chat_block(block)

    assert normalized_messages == [{"role": "system", "content": "Hello"}]
    assert "[[[System]]]" in rendered
    assert rendered.rstrip().endswith("[[[/Assistant]]]")
    assert "[[[Assistant*]]]" not in rendered


def test_chat_user_followup_block_normalizes_config_tags():
    app = make_app()
    app.cfg["chat_user"] = "User*"

    block_text, cursor_offset = app._chat_user_followup_block()

    assert "[[[User]]]" in block_text
    assert block_text.rstrip().endswith("[[[/User]]]")
    assert cursor_offset == len("\n\n[[[User]]]\n")
