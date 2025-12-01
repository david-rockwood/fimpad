from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


DialogMode = Literal["open", "save"]


@dataclass
class FileDialogAdapter:
    """Bridges file dialog logic to a concrete UI implementation."""

    set_path: Callable[[str], None]
    clear_items: Callable[[], None]
    add_item: Callable[[str, str, bool], str]
    set_action_enabled: Callable[[bool], None]
    set_filename: Callable[[str], None] | None = None
    focus_item: Callable[[str], None] | None = None
    reset_scroll: Callable[[], None] | None = None


class FileDialogController:
    """Shared controller for open/save dialogs.

    The controller is UI-agnostic; the :class:`FileDialogAdapter` provides the
    concrete widget operations. The controller tracks directory traversal,
    hidden-file filtering, and directory creation while delegating selection
    handling to the caller via ``on_accept``.
    """

    def __init__(
        self,
        *,
        mode: DialogMode,
        initial_dir: str,
        show_hidden: bool,
        adapter: FileDialogAdapter,
        on_error: Callable[[str, str, str | None], None],
        on_accept: Callable[[str], None],
        prompt_directory_name: Callable[[], str | None],
        filename_getter: Callable[[], str] | None = None,
    ) -> None:
        if mode == "save" and filename_getter is None:
            raise ValueError("filename_getter is required for save dialogs")

        self.mode = mode
        self.adapter = adapter
        self.on_error = on_error
        self.on_accept = on_accept
        self.prompt_directory_name = prompt_directory_name
        self.filename_getter = filename_getter
        self.show_hidden = show_hidden
        self.current_dir = os.path.abspath(initial_dir)
        self.item_paths: dict[str, str] = {}
        self.selected_item: str | None = None

    def _visible_entries(self, path: str) -> list[os.DirEntry[str]]:
        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            title = "Open Error" if self.mode == "open" else "Save Error"
            self.on_error(title, "Could not list directory.", detail=str(exc))
            return []

        visible: list[os.DirEntry[str]] = []
        for entry in entries:
            if not self.show_hidden and entry.name.startswith("."):
                continue
            visible.append(entry)
        return visible

    def _sort_key(self, entry: os.DirEntry[str]) -> tuple[int, str]:
        return (0 if entry.is_dir(follow_symlinks=False) else 1, entry.name.lower())

    def refresh_dir(self, path: str, *, focus_path: str | None = None) -> None:
        visible_entries = self._visible_entries(path)
        if not visible_entries and not os.path.exists(path):
            return

        self.current_dir = os.path.abspath(path)
        self.adapter.set_path(self.current_dir)
        self.adapter.clear_items()
        self.item_paths.clear()
        self.selected_item = None

        for entry in sorted(visible_entries, key=self._sort_key):
            item_id = self.adapter.add_item(
                entry.name, entry.path, entry.is_dir(follow_symlinks=False)
            )
            self.item_paths[item_id] = entry.path

        if focus_path and self.adapter.focus_item:
            for item_id, item_path in self.item_paths.items():
                if item_path == focus_path:
                    self.adapter.focus_item(item_id)
                    break

        if self.adapter.reset_scroll:
            self.adapter.reset_scroll()

        self.update_action_state()

    def set_show_hidden(self, show: bool) -> None:
        self.show_hidden = show
        self.refresh_dir(self.current_dir)

    def go_parent(self) -> None:
        parent = os.path.dirname(self.current_dir) or self.current_dir
        self.refresh_dir(parent)

    def _update_filename_from_path(self, path: str) -> None:
        if self.adapter.set_filename and os.path.isfile(path):
            self.adapter.set_filename(os.path.basename(path))

    def on_selection(self, item_id: str | None) -> None:
        self.selected_item = item_id
        selected_path = self.item_paths.get(item_id or "")
        if selected_path and self.mode == "save":
            self._update_filename_from_path(selected_path)
        self.update_action_state()

    def update_action_state(self) -> None:
        enabled = False
        if self.mode == "open":
            selected_path = self.item_paths.get(self.selected_item or "")
            enabled = bool(selected_path and os.path.isfile(selected_path))
        else:
            assert self.filename_getter is not None
            enabled = bool(self.filename_getter().strip())
        self.adapter.set_action_enabled(enabled)

    def on_filename_change(self) -> None:
        if self.mode == "save":
            self.update_action_state()

    def activate_selection(self, item_id: str | None) -> None:
        path = self.item_paths.get(item_id or "")
        if not path:
            return
        if os.path.isdir(path):
            self.refresh_dir(path)
            return
        if self.mode == "save":
            self._update_filename_from_path(path)
            self.accept_path()
            return
        self.selected_item = item_id
        self.accept_path()

    def accept_path(self) -> None:
        if self.mode == "open":
            path = self.item_paths.get(self.selected_item or "")
            if path and os.path.isfile(path):
                self.on_accept(path)
            return

        assert self.filename_getter is not None
        name = self.filename_getter().strip()
        if not name:
            return
        self.on_accept(os.path.join(self.current_dir, name))

    def create_directory(self) -> None:
        name = self.prompt_directory_name()
        if not name:
            return
        new_path = os.path.join(self.current_dir, name)
        try:
            os.makedirs(new_path, exist_ok=False)
        except OSError as exc:
            self.on_error(
                "Create Directory Error",
                "Could not create directory.",
                detail=str(exc),
            )
            return
        self.refresh_dir(new_path, focus_path=new_path)
