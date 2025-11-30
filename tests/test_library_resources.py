from fimpad.library_resources import iter_library


def test_library_entries_keep_extensions():
    library = iter_library()

    assert library, "expected bundled library resources"

    for entries in library.values():
        for title, resource in entries:
            assert title == resource.name

    fimpad_titles = {title for title, _ in library.get("FIMpad", [])}
    assert "Shortcuts.md" in fimpad_titles
