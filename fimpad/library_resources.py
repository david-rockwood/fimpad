"""Helpers for discovering bundled library files.

Add new ``.txt`` or ``.md`` files to ``fimpad/library`` (optionally inside a
    single-level subdirectory) to have them bundled and discovered automatically.
"""

import contextlib
import pathlib
import sys
from importlib import resources
from importlib.resources.abc import Traversable

_LIBRARY_EXTS = {".txt", ".md"}


def iter_library() -> dict[str | None, list[tuple[str, Traversable]]]:
    """Return bundled library files grouped by subdirectory.

    Library files are discovered under ``fimpad/library`` and include regular
    ``.txt`` and ``.md`` files. Files placed directly inside ``fimpad/library``
    are grouped under ``None`` (the top-level menu), while files inside a
    single-level subdirectory are grouped under that directory's name. Filenames
    are normalized to lowercase for sorting, and the returned title includes the
    file extension.
    """

    with contextlib.ExitStack() as stack:
        library_dir = _resolve_library_dir(stack)
        if library_dir is None:
            return {}

        results: dict[str | None, list[tuple[str, Traversable]]] = {}

        def add_entry(group: str | None, entry: pathlib.Path) -> None:
            if not entry.is_file():
                return
            if entry.suffix.lower() not in _LIBRARY_EXTS:
                return
            results.setdefault(group, []).append((entry.name, entry))

        for entry in library_dir.iterdir():
            if entry.is_dir():
                for nested in entry.iterdir():
                    add_entry(entry.name, nested)
                continue
            add_entry(None, entry)

        for entries in results.values():
            entries.sort(key=lambda item: item[0].lower())

        return dict(
            sorted(results.items(), key=lambda item: (item[0] is not None, item[0] or ""))
        )


def _resolve_library_dir(stack: contextlib.ExitStack) -> pathlib.Path | None:
    """Locate the packaged library directory.

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
            library_dir = stack.enter_context(
                resources.as_file(package_files.joinpath("library"))
            )
            if library_dir.exists():
                return library_dir

    if getattr(sys, "frozen", False):
        base = pathlib.Path(getattr(sys, "_MEIPASS", ""))
        pyinstaller_dir = base / "fimpad" / "library"
        if pyinstaller_dir.exists():
            return pyinstaller_dir

    return None
