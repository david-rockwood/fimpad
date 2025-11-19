"""Helpers for discovering bundled example files.

Add new ``.txt`` or ``.md`` examples to ``fimpad/examples`` to have them bundled and
discovered automatically.
"""

import contextlib
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
        package_files = resources.files(__package__)
    except Exception:
        return []

    with contextlib.ExitStack() as stack:
        try:
            examples_dir = stack.enter_context(
                resources.as_file(package_files.joinpath("examples"))
            )
        except FileNotFoundError:
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
