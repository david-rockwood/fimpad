from fimpad.help import get_help_template


def test_help_template_contains_user_markers():
    template = get_help_template()
    assert "[[[user]]]" in template
    assert "[[[/user]]]" in template
