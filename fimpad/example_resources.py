"""Helpers for discovering bundled example files.

Add new ``.txt`` or ``.md`` examples to ``fimpad/examples`` to have them bundled and
discovered automatically.
"""

import contextlib
import pathlib
import sys
from importlib import resources
from importlib.resources.abc import Traversable

_EXAMPLE_EXTS = {".txt", ".md"}


def iter_examples() -> list[tuple[str, Traversable]]:
    """Return bundled examples as ``(title, resource)`` pairs.

    Examples are discovered under ``fimpad/examples`` and include regular ``.txt``
    and ``.md`` files. Filenames are normalized to lowercase for sorting, and the
    returned title omits the file extension.
    """

    with contextlib.ExitStack() as stack:
        examples_dir = _resolve_examples_dir(stack)
        if examples_dir is None:
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


def _resolve_examples_dir(stack: contextlib.ExitStack) -> pathlib.Path | None:
    """Locate the packaged examples directory.

    The primary lookup uses ``importlib.resources`` so that editable/source installs
    work as expected. In frozen (PyInstaller) binaries, fall back to the extracted
    ``_MEIPASS`` payload.
    """

    package_files: Traversable | None
    try:
        package_files = resources.files(__package__)
    except Exception:
        package_files = None

    if package_files is not None:
        with contextlib.suppress(FileNotFoundError):
            examples_dir = stack.enter_context(
                resources.as_file(package_files.joinpath("examples"))
            )
            if examples_dir.exists():
                return examples_dir

    if getattr(sys, "frozen", False):
        base = pathlib.Path(getattr(sys, "_MEIPASS", ""))
        pyinstaller_dir = base / "fimpad" / "examples"
        if pyinstaller_dir.exists():
            return pyinstaller_dir

    return None
