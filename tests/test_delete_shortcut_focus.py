from fimpad.app import FIMPad


def test_delete_shortcut_requires_text_focus():
    app = object.__new__(FIMPad)

    handled = []
    dummy_text = object()

    app._current_text_widget = lambda: dummy_text
    app.focus_get = lambda: dummy_text

    handler = app._make_shortcut_handler(lambda: handled.append(True), require_text_focus=True)

    assert handler() == "break"
    assert handled == [True]


def test_delete_shortcut_ignored_without_text_focus():
    app = object.__new__(FIMPad)

    handled = []
    dummy_text = object()

    app._current_text_widget = lambda: dummy_text
    app.focus_get = lambda: object()

    handler = app._make_shortcut_handler(lambda: handled.append(True), require_text_focus=True)

    assert handler() is None
    assert handled == []
