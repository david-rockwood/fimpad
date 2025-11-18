from fimpad.help import get_help_template


def test_help_template_mentions_fim_tags():
    template = get_help_template()
    assert "[[[" in template
    assert "[[[prefix]]]" in template or "prefix" in template.lower()
