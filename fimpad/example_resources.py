"""Helpers for discovering bundled example files."""

from importlib import resources
from importlib.resources.abc import Traversable

_EXAMPLE_EXTS = {".txt", ".md"}


def iter_examples() -> list[tuple[str, Traversable]]:
    """Return bundled examples as ``(title, resource)`` pairs.

    Examples are discovered under ``fimpad/examples`` and include regular ``.txt``
    and ``.md`` files. Filenames are normalized to lowercase for sorting, and the
    returned title omits the file extension.
    """

    try:
        examples_dir = resources.files(__package__).joinpath("examples")
    except Exception:
        return []

    if not examples_dir.exists():
        return []

    results: list[tuple[str, Traversable]] = []
    for entry in examples_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in _EXAMPLE_EXTS:
            continue
        results.append((entry.stem, entry))

    results.sort(key=lambda item: item[0].lower())
    return results
