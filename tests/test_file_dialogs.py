from __future__ import annotations

import os
from pathlib import Path

from fimpad.ui.file_dialogs import FileDialogAdapter, FileDialogController


class FakeAdapter:
    def __init__(self) -> None:
        self.path: str | None = None
        self.items: list[tuple[str, str, str, bool]] = []
        self.action_enabled = False
        self.filename = ""
        self.focused: str | None = None
        self.reset_called = False

    def set_path(self, path: str) -> None:
        self.path = path

    def clear_items(self) -> None:
        self.items.clear()

    def add_item(self, name: str, path: str, is_dir: bool) -> str:
        item_id = f"item-{len(self.items)}"
        self.items.append((item_id, name, path, is_dir))
        return item_id

    def set_action_enabled(self, enabled: bool) -> None:
        self.action_enabled = enabled

    def set_filename(self, name: str) -> None:
        self.filename = name

    def focus_item(self, item_id: str) -> None:
        self.focused = item_id

    def reset_scroll(self) -> None:
        self.reset_called = True

    def make_adapter(self) -> FileDialogAdapter:
        return FileDialogAdapter(
            set_path=self.set_path,
            clear_items=self.clear_items,
            add_item=self.add_item,
            set_action_enabled=self.set_action_enabled,
            set_filename=self.set_filename,
            focus_item=self.focus_item,
            reset_scroll=self.reset_scroll,
        )

    def path_for(self, name: str) -> str | None:
        for item_id, item_name, _item_path, _ in self.items:
            if item_name == name:
                return item_id
        return None


def test_open_dialog_controller_flow(tmp_path: Path):
    files = {
        "alpha.txt": "a",
        "beta.txt": "b",
        "visible": None,
        ".hidden": None,
    }
    for name, content in files.items():
        path = tmp_path / name
        if content is None:
            path.mkdir()
        else:
            path.write_text(content, encoding="utf-8")

    adapter = FakeAdapter()
    accepted: list[str] = []
    errors: list[tuple[str, str]] = []

    controller = FileDialogController(
        mode="open",
        initial_dir=str(tmp_path),
        show_hidden=False,
        adapter=adapter.make_adapter(),
        on_error=lambda title, message, detail=None: errors.append((title, message)),
        on_accept=accepted.append,
        prompt_directory_name=lambda: "created",
    )

    controller.refresh_dir(str(tmp_path))

    assert adapter.path == os.path.abspath(tmp_path)
    names = {name for _, name, _, _ in adapter.items}
    assert "alpha.txt" in names and ".hidden" not in names
    assert adapter.action_enabled is False

    controller.set_show_hidden(True)
    names = {name for _, name, _, _ in adapter.items}
    assert ".hidden" in names

    created_path = adapter.path_for("created")
    assert created_path is None
    controller.create_directory()
    created_dir = tmp_path / "created"
    assert created_dir.is_dir()
    assert controller.current_dir == os.path.abspath(created_dir)

    controller.go_parent()
    assert controller.current_dir == os.path.abspath(tmp_path)

    alpha_id = adapter.path_for("alpha.txt")
    assert alpha_id is not None
    controller.on_selection(alpha_id)
    assert adapter.action_enabled is True
    controller.accept_path()
    assert accepted == [str(tmp_path / "alpha.txt")]
    assert errors == []


def test_save_dialog_controller_tracks_filename(tmp_path: Path):
    existing = tmp_path / "note.md"
    existing.write_text("hi", encoding="utf-8")
    tmp_path.joinpath("subdir").mkdir()

    adapter = FakeAdapter()
    adapter.filename = "draft.txt"
    accepted: list[str] = []
    errors: list[str] = []

    controller = FileDialogController(
        mode="save",
        initial_dir=str(tmp_path),
        show_hidden=False,
        adapter=adapter.make_adapter(),
        on_error=lambda *_args, **_kwargs: errors.append("error"),
        on_accept=accepted.append,
        prompt_directory_name=lambda: None,
        filename_getter=lambda: adapter.filename,
    )

    controller.refresh_dir(str(tmp_path))
    assert adapter.action_enabled is True

    note_id = adapter.path_for("note.md")
    assert note_id is not None
    controller.on_selection(note_id)
    assert adapter.filename == "note.md"

    controller.on_filename_change()
    controller.accept_path()
    assert accepted == [str(tmp_path / "note.md")]

    controller.go_parent()  # Should not error at filesystem root boundaries
    assert errors == []
