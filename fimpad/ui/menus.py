import tkinter as tk
from tkinter import ttk


class AppMenus:
    def __init__(self, app):
        self.app = app
        self.menubar = tk.Menu(app)
        self._build_menus()

    def _build_menus(self) -> None:
        app = self.app
        menubar = self.menubar

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New Tab", accelerator="Ctrl+N", command=app._new_tab)
        filemenu.add_command(
            label="Open…", accelerator="Ctrl+O", command=app._open_file_into_current
        )
        filemenu.add_command(label="Save", accelerator="Ctrl+S", command=app._save_file_current)
        filemenu.add_command(
            label="Save As…", accelerator="Ctrl+Shift+S", command=app._save_file_as_current
        )
        filemenu.add_separator()
        filemenu.add_command(
            label="Close Tab", accelerator="Ctrl+W", command=app._close_current_tab
        )
        filemenu.add_separator()
        filemenu.add_command(label="Quit", accelerator="Ctrl+Q", command=app._on_close)
        menubar.add_cascade(label="File", menu=filemenu)

        editmenu = tk.Menu(menubar, tearoff=0)
        editmenu.add_command(
            label="Undo",
            accelerator="Ctrl+Z",
            command=lambda: app._cur_text().event_generate("<<Undo>>"),
        )
        editmenu.add_command(
            label="Redo",
            accelerator="Ctrl+Shift+Z",
            command=lambda: app._cur_text().event_generate("<<Redo>>"),
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Cut",
            accelerator="Ctrl+X",
            command=lambda: app._cur_text().event_generate("<<Cut>>"),
        )
        editmenu.add_command(
            label="Copy",
            accelerator="Ctrl+C",
            command=lambda: app._cur_text().event_generate("<<Copy>>"),
        )
        editmenu.add_command(
            label="Paste",
            accelerator="Ctrl+V",
            command=lambda: app._cur_text().event_generate("<<Paste>>"),
        )
        editmenu.add_command(
            label="Delete",
            accelerator="Del",
            command=lambda: app._cur_text().event_generate("<<Clear>>"),
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Select All", accelerator="Ctrl+A", command=app._select_all_current
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Find & Replace…", accelerator="Ctrl+F", command=app._open_replace_dialog
        )
        editmenu.add_command(
            label="Regex & Replace…", accelerator="Ctrl+R", command=app._open_regex_replace_dialog
        )
        editmenu.add_command(
            label="BOL Tool…", accelerator="Ctrl+B", command=app._open_bol_tool
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Settings…", accelerator="Ctrl+G", command=app._open_settings
        )
        menubar.add_cascade(label="Edit", menu=editmenu)

        togglemenu = tk.Menu(menubar, tearoff=0)
        self.wrap_menu_var = tk.BooleanVar(value=True)
        togglemenu.add_checkbutton(
            label="Wrap",
            accelerator="Alt+W",
            variable=self.wrap_menu_var,
            command=app._on_wrap_menu_toggled,
        )
        self.follow_menu_var = tk.BooleanVar(value=app.cfg.get("follow_stream_enabled", True))
        togglemenu.add_checkbutton(
            label="Follow Stream",
            accelerator="Alt+F",
            variable=self.follow_menu_var,
            command=app._on_follow_menu_toggled,
        )
        self.line_numbers_menu_var = tk.BooleanVar(
            value=app.cfg.get("line_numbers_enabled", False)
        )
        togglemenu.add_checkbutton(
            label="Line Numbers",
            accelerator="Alt+N",
            variable=self.line_numbers_menu_var,
            command=app._toggle_line_numbers,
        )
        self.spell_menu_var = tk.BooleanVar(value=app.cfg.get("spellcheck_enabled", True))
        togglemenu.add_checkbutton(
            label="Spellcheck",
            accelerator="Alt+S",
            variable=self.spell_menu_var,
            command=app._toggle_spellcheck,
        )
        menubar.add_cascade(label="Toggle", menu=togglemenu)

        aimenu = tk.Menu(menubar, tearoff=0)
        aimenu.add_command(
            label="Generate",
            accelerator="Alt+G",
            command=app.generate,
        )
        aimenu.add_command(
            label="Repeat Last FIM",
            accelerator="Alt+R",
            command=app.repeat_last_fim,
        )
        aimenu.add_command(
            label="Paste Last FIM Tag",
            accelerator="Alt+P",
            command=app.paste_last_fim_tag,
        )
        aimenu.add_command(
            label="Apply Config Tag",
            accelerator="Alt+C",
            command=app.apply_config_tag,
        )
        aimenu.add_command(
            label="Paste Current Config",
            accelerator="Alt+J",
            command=app.paste_current_config,
        )
        aimenu.add_command(
            label="Interrupt Stream",
            accelerator="Alt+I",
            command=app.interrupt_stream,
        )
        aimenu.add_command(
            label="Validate Tags",
            accelerator="Alt+V",
            command=app.validate_tags_current,
        )
        aimenu.add_command(
            label="Show Log",
            accelerator="Alt+L",
            command=app.show_fim_log,
        )
        menubar.add_cascade(label="AI", menu=aimenu)

        library_menu = tk.Menu(menubar, tearoff=0)
        if not app._library:
            library_menu.add_command(label="(No library files found)", state="disabled")
        else:
            top_level_items = app._library.get(None, [])
            for title, resource in top_level_items:
                library_menu.add_command(
                    label=title,
                    command=lambda t=title, r=resource: app._open_library_resource(t, r),
                )

            for group, entries in app._library.items():
                if group is None:
                    continue
                submenu = tk.Menu(library_menu, tearoff=0)
                for title, resource in entries:
                    submenu.add_command(
                        label=title,
                        command=lambda t=title, r=resource: app._open_library_resource(t, r),
                    )
                library_menu.add_cascade(label=group, menu=submenu)
        menubar.add_cascade(label="Library", menu=library_menu)

    def attach(self) -> None:
        self.app.config(menu=self.menubar)

