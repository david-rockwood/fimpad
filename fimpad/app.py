#!/usr/bin/env python3
"""
FIMpad — Tabbed Tkinter editor for llama-server
with FIM streaming, dirty tracking, and enchant-based spellcheck.
"""

import contextlib
import os
import queue
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from importlib import resources
from importlib.resources.abc import Traversable
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import enchant

from .client import stream_completion
from .config import DEFAULTS, WORD_RE, load_config, save_config
from .example_resources import iter_examples
from .parser import MARKER_REGEX, FIMRequest, parse_fim_request
from .utils import offset_to_tkindex


class FIMPad(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FIMpad")
        self.geometry("1100x750")

        self.cfg = load_config()
        self.app_font = tkfont.Font(family=self.cfg["font_family"], size=self.cfg["font_size"])

        try:
            self.style = ttk.Style(self)
            if "clam" in self.style.theme_names():
                self.style.theme_use("clam")
        except Exception:
            pass
        self._tab_close_image = None
        self._tab_close_image_active = None
        self._tab_close_support = "element"  # "element" or "compound"
        self._tab_close_hit_padding = 12
        self._tab_close_compound_padding = (12, 6, 32, 6)
        self._tab_close_hover_tab: str | None = None

        self._examples = iter_examples()
        self._spell_menu_var: tk.BooleanVar | None = None
        self._wrap_menu_var: tk.BooleanVar | None = None
        self._build_menu()
        self._build_notebook()
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._result_queue = queue.Queue()
        self.after(60, self._poll_queue)

        self._spell_notice_msg: str | None = None
        self._spell_notice_last: str | None = None
        self._dictionary = self._load_dictionary(self.cfg.get("spell_lang", "en_US"))
        self._spell_ignore = set()  # session-level ignores

        self._last_fim_marker: str | None = None

        self._new_tab()
        self.after_idle(lambda: self._schedule_spellcheck_for_frame(self.nb.select(), delay_ms=50))

        # Keys
        self.bind_all("<Control-n>", lambda e: self._new_tab())
        self.bind_all("<Control-o>", lambda e: self._open_file_into_current())
        self.bind_all("<Control-s>", lambda e: self._save_file_current())
        self.bind_all("<Control-Shift-S>", lambda e: self._save_file_as_current())
        self.bind_all("<Control-q>", lambda e: self._on_close())
        self.bind_all("<Control-Return>", self._on_generate_shortcut)
        self.bind_all("<Control-Shift-Return>", self._on_repeat_last_fim_shortcut)
        self.bind_all("<Control-Shift-KP_Enter>", self._on_repeat_last_fim_shortcut)
        self.bind_all("<Control-f>", lambda e: self._open_find_dialog())
        self.bind_all("<Control-h>", lambda e: self._open_replace_dialog())
        self.bind_all("<Control-w>", lambda e: self._close_current_tab())  # close tab
        self.bind_all("<Alt-z>", lambda e: self._toggle_wrap_current())  # wrap toggle
        self.bind_all("<Alt-s>", lambda e: self._toggle_spellcheck())  # spell toggle
        self.bind_all("<Control-a>", lambda e: self._select_all_current())  # select all
        self.bind_all("<Control-t>", lambda e: self._open_settings())

        for idx in range(1, 10):
            self.bind_all(
                f"<Alt-Key-{idx}>",
                lambda e, index=idx - 1: self._select_tab_by_index(index),
            )
        self.bind_all("<Alt-Key-0>", lambda e: self._select_tab_by_index(9))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- Notebook / Tabs ----------

    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)
        self.nb.enable_traversal()
        self.tabs = {}  # frame -> state dict
        self._setup_closable_tabs()

    def _setup_closable_tabs(self) -> None:
        try:
            style = self.style
        except AttributeError:
            style = ttk.Style(self)
            self.style = style

        if self._tab_close_image is None or self._tab_close_image_active is None:
            self._tab_close_image = self._create_close_image(
                fill="#555555", size=18, margin=4, stroke=2
            )
            self._tab_close_image_active = self._create_close_image(
                fill="#cc3333", size=18, margin=4, stroke=2
            )

        created_custom_element = True
        try:
            style.element_create(
                "Notebook.close",
                "image",
                self._tab_close_image,
                ("active", self._tab_close_image_active),
                ("pressed", self._tab_close_image_active),
            )
        except tk.TclError:
            created_custom_element = False

        if created_custom_element:
            try:
                style.layout(
                    "ClosableNotebook.TNotebook.Tab",
                    [
                        (
                            "Notebook.tab",
                            {
                                "sticky": "nswe",
                                "children": [
                                    (
                                        "Notebook.padding",
                                        {
                                            "side": "top",
                                            "sticky": "nswe",
                                            "children": [
                                                (
                                                    "Notebook.focus",
                                                    {
                                                        "side": "top",
                                                        "sticky": "nswe",
                                                        "children": [
                                                            (
                                                                "Notebook.label",
                                                                {
                                                                    "side": "left",
                                                                    "sticky": "",
                                                                    "padding": (0, 0, 6, 0),
                                                                },
                                                            ),
                                                            (
                                                                "Notebook.close",
                                                                {
                                                                    "side": "right",
                                                                    "sticky": "",
                                                                    "padding": (4, 2, 6, 2),
                                                                },
                                                            ),
                                                        ],
                                                    },
                                                )
                                            ],
                                        },
                                    )
                                ],
                            },
                        )
                    ],
                )
                style.configure("ClosableNotebook.TNotebook.Tab", padding=(12, 6, 32, 6))
                style.layout("ClosableNotebook.TNotebook", style.layout("TNotebook"))
            except tk.TclError:
                created_custom_element = False

        if created_custom_element:
            self.nb.configure(style="ClosableNotebook.TNotebook")
            self.nb.bind("<Button-1>", self._handle_tab_close_click, add="+")
            self._tab_close_support = "element"
        else:
            # Fallback for environments that cannot create custom themed elements
            self._tab_close_support = "compound"
            self.nb.bind("<Button-1>", self._handle_tab_close_click, add="+")
            self.nb.bind("<Motion>", self._handle_tab_motion, add="+")
            self.nb.bind("<Leave>", lambda e: self._set_close_hover_tab(None), add="+")

    def _create_close_image(
        self, fill: str, size: int = 12, margin: int = 2, stroke: int = 1
    ) -> tk.PhotoImage:
        img = tk.PhotoImage(width=size, height=size)
        background = self.cfg.get("bg", "#f0f0f0")
        img.put(background, to=(0, 0, size, size))
        span = max(size - (margin * 2), 2)

        def _put(px: int, py: int):
            if 0 <= px < size and 0 <= py < size:
                img.put(fill, to=(px, py))

        for i in range(span):
            x = margin + i
            y = margin + i
            x2 = size - 1 - margin - i
            y2 = margin + i
            for offset in range(stroke):
                _put(x + offset, y)
                _put(x, y + offset)
                _put(x2 - offset, y2)
                _put(x2, y2 + offset)
        return img

    def _handle_tab_close_click(self, event):
        try:
            index = self.nb.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        tabs = self.nb.tabs()
        if index < 0 or index >= len(tabs):
            return
        tab_id = tabs[index]
        print(
            f"[TABCLOSE] click index={index} tab_id={tab_id} support={self._tab_close_support}",
            flush=True,
        )
        if self._tab_close_support == "element":
            element_tail = self._identify_tab_element(event.x, event.y)
            print(f"[TABCLOSE] themed element_tail={element_tail!r}", flush=True)
            if "close" not in element_tail:
                print("[TABCLOSE] themed click ignored; not on close element", flush=True)
                return
        else:
            hit = self._is_fallback_close_hit(event.x, event.y, tab_id)
            print(
                f"[TABCLOSE] fallback hit_test={hit} x={event.x} y={event.y} tab={tab_id}",
                flush=True,
            )
            if not hit:
                return
        if self._tab_close_support == "compound":
            self._set_close_hover_tab(None)
        self.nb.select(tab_id)
        print(f"[TABCLOSE] invoking close for tab_id={tab_id}", flush=True)
        self._close_current_tab()

    def _handle_tab_motion(self, event):
        if self._tab_close_support != "compound":
            return
        try:
            index = self.nb.index(f"@{event.x},{event.y}")
        except tk.TclError:
            self._set_close_hover_tab(None)
            return
        tabs = self.nb.tabs()
        if index < 0 or index >= len(tabs):
            self._set_close_hover_tab(None)
            return
        tab_id = tabs[index]
        if self._is_fallback_close_hit(event.x, event.y, tab_id):
            self._set_close_hover_tab(tab_id)
        else:
            self._set_close_hover_tab(None)

    def _set_close_hover_tab(self, tab_id: str | None):
        if self._tab_close_support != "compound":
            return
        new_tab = str(tab_id) if tab_id is not None else None
        if new_tab == self._tab_close_hover_tab:
            return
        if self._tab_close_hover_tab is not None:
            with contextlib.suppress(tk.TclError):
                self.nb.tab(self._tab_close_hover_tab, image=self._tab_close_image)
        self._tab_close_hover_tab = new_tab
        if new_tab is not None:
            with contextlib.suppress(tk.TclError):
                self.nb.tab(new_tab, image=self._tab_close_image_active)

    def _apply_tab_title(self, tab_id, title: str) -> None:
        tab_name = str(tab_id)
        kwargs: dict[str, object] = {"text": title}
        if self._tab_close_support == "compound":
            image = (
                self._tab_close_image_active
                if tab_name == self._tab_close_hover_tab
                else self._tab_close_image
            )
            kwargs.update(
                image=image,
                compound=tk.RIGHT,
                padding=self._tab_close_compound_padding,
            )
        self.nb.tab(tab_name, **kwargs)

    def _identify_tab_element(self, x: int, y: int) -> str:
        try:
            element = self.nb.tk.call(self.nb._w, "identify", "element", x, y)
        except tk.TclError:
            return ""
        element_tail = str(element or "").split(".")[-1].lower()
        return element_tail

    def _is_fallback_close_hit(self, x: int, y: int, tab_id: str) -> bool:
        if self._tab_close_support != "compound" or self._tab_close_image is None:
            return False
        try:
            tab_index = self.nb.index(tab_id)
        except tk.TclError:
            return False
        with contextlib.suppress(tk.TclError):
            bbox = self.nb.bbox(tab_index)
        if not bbox:
            print(
                f"[TABCLOSE] fallback bbox missing tab={tab_id} index={tab_index}",
                flush=True,
            )
            return False
        tab_x, tab_y, width, height = bbox
        image_width = self._tab_close_image.width()
        padding = self._tab_close_hit_padding
        right_pad = 0
        if self._tab_close_compound_padding:
            right_pad = self._tab_close_compound_padding[2]
        button_right = tab_x + width
        button_width = image_width + right_pad
        button_left = button_right - button_width
        print(
            "[TABCLOSE] fallback bbox"
            f" tab={tab_id} bbox={bbox} button_left={button_left}"
            f" button_right={button_right} padding={padding}",
            flush=True,
        )
        return (
            button_left - padding <= x <= button_right + padding
            and tab_y <= y <= tab_y + height
        )

    def _new_tab(self, content: str = "", title: str = "Untitled"):
        frame = ttk.Frame(self.nb)
        text = ScrolledText(frame, undo=True, maxundo=-1, wrap=tk.WORD)
        text.pack(fill=tk.BOTH, expand=True)
        text.configure(
            font=self.app_font,
            fg=self.cfg["fg"],
            bg=self.cfg["bg"],
            insertbackground=self.cfg["fg"],
        )
        self._apply_editor_padding(text, self.cfg["editor_padding_px"])
        self._clear_line_spacing(text)

        # Spellcheck tag + bindings
        text.tag_configure("misspelled", underline=True, foreground="#ff6666")
        text.bind(
            "<Button-3>", lambda e, fr=frame: self._spell_context_menu(e, fr)
        )  # right-click menu
        text.bind("<KeyRelease>", lambda e, fr=frame: self._schedule_spellcheck_for_frame(fr))
        text.bind("<Control-Return>", self._on_generate_shortcut)
        text.bind("<Control-KP_Enter>", self._on_generate_shortcut)
        text.bind("<Control-Shift-Return>", self._on_repeat_last_fim_shortcut)
        text.bind("<Control-Shift-KP_Enter>", self._on_repeat_last_fim_shortcut)

        st = {
            "path": None,
            "text": text,
            "wrap": "word",  # "word" or "none"
            "dirty": False,
            "suppress_modified": False,
            "_spell_timer": None,
            "stream_buffer": [],
            "stream_flush_job": None,
            "stream_mark": None,
            "stream_following": False,
            "_stream_follow_primed": False,
            "stops_after": [],
            "stops_after_maxlen": 0,
            "stream_tail": "",
            "stream_cancelled": False,
        }

        def on_modified(event=None):
            if st["suppress_modified"]:
                text.edit_modified(False)
                return
            if text.edit_modified():
                self._set_dirty(st, True)
                text.edit_modified(False)

        text.bind("<<Modified>>", on_modified)

        st["suppress_modified"] = True
        text.insert("1.0", content)
        text.edit_modified(False)
        st["suppress_modified"] = False

        self.tabs[frame] = st
        self.nb.add(frame, text=title)
        self._apply_tab_title(frame, title)
        self.nb.select(frame)

        text.focus_set()
        text.mark_set("insert", "1.0")
        text.see("1.0")

        # Initial spellcheck (debounced)
        self._schedule_spellcheck_for_frame(frame, delay_ms=250)
        self._sync_wrap_menu_var()

    def _on_tab_changed(self, event=None):
        current = self.nb.select()
        if current:
            self._schedule_spellcheck_for_frame(current, delay_ms=80)
        self._sync_wrap_menu_var()

    def _current_tab_state(self):
        tab = self.nb.select()
        if not tab:
            return None
        frame = self.nametowidget(tab)
        return self.tabs.get(frame)

    def _update_tab_title(self, st):
        tab = self.nb.select()
        if not tab:
            return
        title = os.path.basename(st["path"]) if st["path"] else "Untitled"
        if st.get("dirty"):
            title = f"• {title}"
        self._apply_tab_title(tab, title)

    def _set_dirty(self, st, dirty: bool):
        st["dirty"] = dirty
        self._update_tab_title(st)

    def _close_current_tab(self):
        st = self._current_tab_state()
        if not st:
            return
        if not self._maybe_save(st):
            return
        cur = self.nb.select()
        frame = self.nametowidget(cur)
        self.nb.forget(cur)
        self.tabs.pop(frame, None)
        if not self.tabs:
            self._new_tab()

    def _select_tab_by_index(self, index: int) -> None:
        tabs = self.nb.tabs()
        if index < 0 or index >= len(tabs):
            return
        self.nb.select(tabs[index])

    # ---------- Menu / Toolbar ----------

    def _build_menu(self):
        menubar = tk.Menu(self)

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="New Tab", accelerator="Ctrl+N", command=self._new_tab)
        filemenu.add_command(
            label="Open…", accelerator="Ctrl+O", command=self._open_file_into_current
        )
        filemenu.add_command(label="Save", accelerator="Ctrl+S", command=self._save_file_current)
        filemenu.add_command(
            label="Save As…", accelerator="Ctrl+Shift+S", command=self._save_file_as_current
        )
        filemenu.add_separator()
        filemenu.add_command(
            label="Close Tab", accelerator="Ctrl+W", command=self._close_current_tab
        )
        filemenu.add_separator()
        filemenu.add_command(label="Quit", accelerator="Ctrl+Q", command=self._on_close)
        menubar.add_cascade(label="File", menu=filemenu)

        editmenu = tk.Menu(menubar, tearoff=0)
        editmenu.add_command(
            label="Undo",
            accelerator="Ctrl+Z",
            command=lambda: self._cur_text().event_generate("<<Undo>>"),
        )
        editmenu.add_command(
            label="Redo",
            accelerator="Ctrl+Y",
            command=lambda: self._cur_text().event_generate("<<Redo>>"),
        )
        editmenu.add_separator()
        editmenu.add_command(label="Find…", accelerator="Ctrl+F", command=self._open_find_dialog)
        editmenu.add_command(
            label="Find & Replace…", accelerator="Ctrl+H", command=self._open_replace_dialog
        )
        editmenu.add_separator()
        self._wrap_menu_var = tk.BooleanVar(value=True)
        editmenu.add_checkbutton(
            label="Toggle Wrap",
            accelerator="Alt+Z",
            variable=self._wrap_menu_var,
            command=self._on_wrap_menu_toggled,
        )
        self._spell_menu_var = tk.BooleanVar(value=self.cfg.get("spellcheck_enabled", True))
        editmenu.add_checkbutton(
            label="Toggle Spellcheck",
            accelerator="Alt+S",
            variable=self._spell_menu_var,
            command=self._toggle_spellcheck,
        )
        editmenu.add_command(
            label="Select All", accelerator="Ctrl+A", command=self._select_all_current
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Settings…", accelerator="Ctrl+T", command=self._open_settings
        )
        menubar.add_cascade(label="Edit", menu=editmenu)

        aimenu = tk.Menu(menubar, tearoff=0)
        aimenu.add_command(
            label="Generate",
            accelerator="Ctrl+Enter",
            command=self.generate,
        )
        aimenu.add_command(
            label="Repeat Last FIM",
            accelerator="Ctrl+Shift+Enter",
            command=self.repeat_last_fim,
        )
        menubar.add_cascade(label="AI", menu=aimenu)

        examples_menu = tk.Menu(menubar, tearoff=0)
        if not self._examples:
            examples_menu.add_command(label="(No examples found)", state="disabled")
        else:
            for title, resource in self._examples:
                examples_menu.add_command(
                    label=title,
                    command=lambda t=title, r=resource: self._open_example_resource(
                        t, r
                    ),
                )
        menubar.add_cascade(label="Examples", menu=examples_menu)

        self.config(menu=menubar)

    # ---------- Helpers ----------

    def _apply_editor_padding(self, text: ScrolledText, pad_px: int) -> None:
        text.configure(padx=max(0, int(pad_px)), pady=0)

    def _clear_line_spacing(self, text: tk.Text) -> None:
        text.configure(spacing1=0, spacing2=0, spacing3=0)
        for tag in text.tag_names():
            options = {}
            for opt in ("spacing1", "spacing2", "spacing3"):
                value = text.tag_cget(tag, opt)
                if not value:
                    continue
                if value == "0":
                    continue
                try:
                    if float(value) == 0:
                        continue
                except (TypeError, ValueError):
                    pass
                options[opt] = 0
            if options:
                text.tag_configure(tag, **options)

    def _cur_text(self) -> ScrolledText:
        st = self._current_tab_state()
        return st["text"]

    def _toggle_wrap_current(self):
        st = self._current_tab_state()
        if not st:
            return
        wrap_word = st["wrap"] == "none"
        self._apply_wrap_state(st, wrap_word)
        if self._wrap_menu_var is not None:
            self._wrap_menu_var.set(wrap_word)

    def _on_wrap_menu_toggled(self) -> None:
        st = self._current_tab_state()
        if not st or self._wrap_menu_var is None:
            return
        self._apply_wrap_state(st, self._wrap_menu_var.get())

    def _apply_wrap_state(self, st: dict, wrap_word: bool) -> None:
        text = st["text"]
        st["wrap"] = "word" if wrap_word else "none"
        text.config(wrap=tk.WORD if wrap_word else tk.NONE)
        self._apply_editor_padding(text, self.cfg["editor_padding_px"])

    def _sync_wrap_menu_var(self) -> None:
        if self._wrap_menu_var is None:
            return
        st = self._current_tab_state()
        wrap_word = True if not st else st.get("wrap", "word") != "none"
        self._wrap_menu_var.set(wrap_word)

    def _toggle_spellcheck(self):
        enabled = not self.cfg.get("spellcheck_enabled", True)
        self.cfg["spellcheck_enabled"] = enabled
        save_config(self.cfg)
        if self._spell_menu_var is not None:
            self._spell_menu_var.set(enabled)

        if not enabled:
            for st in self.tabs.values():
                timer_id = st.get("_spell_timer")
                if timer_id is not None:
                    with contextlib.suppress(Exception):
                        self.after_cancel(timer_id)
                    st["_spell_timer"] = None
                st["text"].tag_remove("misspelled", "1.0", "end")
            self._spell_notice_msg = None
            return

        self._dictionary = self._dictionary or self._load_dictionary(
            self.cfg.get("spell_lang", "en_US")
        )
        for frame in self.tabs:
            self._schedule_spellcheck_for_frame(frame, delay_ms=120)

    def _select_all_current(self):
        st = self._current_tab_state()
        if not st:
            return
        t = st["text"]
        t.tag_add("sel", "1.0", "end-1c")
        t.mark_set(tk.INSERT, "1.0")
        t.see("1.0")

    # ---------- Examples ----------

    def _open_example_resource(self, title: str, resource: Traversable) -> None:
        try:
            with resources.as_file(resource) as path, open(path, encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            messagebox.showerror("Example Error", f"Failed to load '{title}': {exc}")
            return

        self._new_tab(content=content, title=title)
        st = self._current_tab_state()
        if st:
            st["text"].focus_set()
            st["text"].mark_set("insert", "1.0")

    # ---------- File Ops + Dirty ----------

    def _open_file_into_current(self):
        st = self._current_tab_state()
        if not st:
            return
        if not self._maybe_save(st):
            return
        path = filedialog.askopenfilename()
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = f.read()
            st["suppress_modified"] = True
            st["text"].delete("1.0", tk.END)
            st["text"].insert("1.0", data)
            st["text"].mark_set("insert", "1.0")
            st["text"].focus_set()
            st["text"].edit_modified(False)
            st["suppress_modified"] = False
            st["path"] = path
            self._set_dirty(st, False)
            self._schedule_spellcheck_for_frame(self.nb.select(), delay_ms=200)
        except Exception as e:
            messagebox.showerror("Open Error", str(e))

    def _save_file_current(self):
        st = self._current_tab_state()
        if not st:
            return
        path = st["path"]
        if not path:
            return self._save_file_as_current()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(st["text"].get("1.0", tk.END))
            st["text"].edit_modified(False)
            self._set_dirty(st, False)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_file_as_current(self):
        st = self._current_tab_state()
        if not st:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(st["text"].get("1.0", tk.END))
            st["path"] = path
            st["text"].edit_modified(False)
            self._set_dirty(st, False)
        except Exception as e:
            messagebox.showerror("Save As Error", str(e))

    def _maybe_save(self, st) -> bool:
        if not st.get("dirty"):
            return True
        title = os.path.basename(st["path"]) if st["path"] else "Untitled"
        resp = messagebox.askyesnocancel("Unsaved Changes", f"Save changes to '{title}'?")
        if resp is None:
            return False
        if resp:
            self._save_file_current()
            if st.get("dirty"):
                return False
        return True

    # ---------- Find / Replace ----------

    def _open_find_dialog(self):
        st = self._current_tab_state()
        if not st:
            return
        text = st["text"]

        w = tk.Toplevel(self)
        w.title("Find")
        w.resizable(False, False)
        tk.Label(w, text="Find:").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        patt_var = tk.StringVar()
        e = tk.Entry(w, width=40, textvariable=patt_var)
        e.grid(row=0, column=1, padx=8, pady=8)
        e.focus_set()

        def find_next():
            patt = patt_var.get()
            if not patt:
                return
            start = text.index(tk.INSERT)
            pos = text.search(patt, start, stopindex=tk.END, nocase=False, regexp=False)
            if not pos:
                pos = text.search(patt, "1.0", stopindex=tk.END, nocase=False, regexp=False)
                if not pos:
                    messagebox.showinfo("Find", "Not found.")
                    return
            end = f"{pos}+{len(patt)}c"
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_add("sel", pos, end)
            text.mark_set(tk.INSERT, end)
            text.see(pos)

        ttk.Button(w, text="Find Next", command=find_next).grid(
            row=1, column=1, padx=8, pady=8, sticky="e"
        )

    def _open_replace_dialog(self):
        st = self._current_tab_state()
        if not st:
            return
        text = st["text"]

        w = tk.Toplevel(self)
        w.title("Find & Replace")
        w.resizable(False, False)
        tk.Label(w, text="Find:").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        tk.Label(w, text="Replace:").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        e1 = tk.Entry(w, width=42, textvariable=find_var)
        e2 = tk.Entry(w, width=42, textvariable=repl_var)
        e1.grid(row=0, column=1, padx=8, pady=8)
        e2.grid(row=1, column=1, padx=8, pady=8)
        e1.focus_set()

        def replace_next():
            patt = find_var.get()
            repl = repl_var.get()
            if not patt:
                return
            start = text.index(tk.INSERT)
            pos = text.search(patt, start, stopindex=tk.END)
            if not pos:
                pos = text.search(patt, "1.0", stopindex=tk.END)
                if not pos:
                    messagebox.showinfo("Replace", "No more matches.")
                    return
            end = f"{pos}+{len(patt)}c"
            text.delete(pos, end)
            text.insert(pos, repl)
            text.mark_set(tk.INSERT, f"{pos}+{len(repl)}c")
            text.see(pos)

        def replace_all():
            patt = find_var.get()
            repl = repl_var.get()
            if not patt:
                return
            count = 0
            idx = "1.0"
            while True:
                pos = text.search(patt, idx, stopindex=tk.END)
                if not pos:
                    break
                end = f"{pos}+{len(patt)}c"
                text.delete(pos, end)
                text.insert(pos, repl)
                idx = f"{pos}+{len(repl)}c"
                count += 1
            messagebox.showinfo("Replace All", f"Replaced {count} occurrences.")

        ttk.Button(w, text="Replace Next", command=replace_next).grid(
            row=2, column=1, padx=8, pady=6, sticky="w"
        )
        ttk.Button(w, text="Replace All", command=replace_all).grid(
            row=2, column=1, padx=8, pady=6, sticky="e"
        )

    # ---------- Settings ----------

    def _open_settings(self):
        cfg = self.cfg
        w = tk.Toplevel(self)
        w.title("Settings — FIMpad")
        w.resizable(False, False)

        def add_row(r, label, var, width=42):
            tk.Label(w, text=label, anchor="w").grid(row=r, column=0, sticky="w", padx=8, pady=4)
            e = tk.Entry(w, textvariable=var, width=width)
            e.grid(row=r, column=1, padx=8, pady=4)
            return e

        endpoint_var = tk.StringVar(value=cfg["endpoint"])
        model_var = tk.StringVar(value=cfg["model"])
        temp_var = tk.StringVar(value=str(cfg["temperature"]))
        top_p_var = tk.StringVar(value=str(cfg["top_p"]))
        defN_var = tk.StringVar(value=str(cfg["default_n"]))

        fim_pref_var = tk.StringVar(value=cfg["fim_prefix"])
        fim_suf_var = tk.StringVar(value=cfg["fim_suffix"])
        fim_mid_var = tk.StringVar(value=cfg["fim_middle"])

        fontfam_var = tk.StringVar(value=cfg["font_family"])
        fontsize_var = tk.StringVar(value=str(cfg["font_size"]))
        pad_var = tk.StringVar(
            value=str(cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"]))
        )
        fg_var = tk.StringVar(value=cfg["fg"])
        bg_var = tk.StringVar(value=cfg["bg"])

        spell_lang_var = tk.StringVar(value=cfg.get("spell_lang", "en_US"))

        row = 0
        add_row(row, "Endpoint (base, no path):", endpoint_var)
        row += 1
        add_row(row, "Model:", model_var)
        row += 1
        add_row(row, "Temperature:", temp_var)
        row += 1
        add_row(row, "Top-p:", top_p_var)
        row += 1
        add_row(row, "Default [[[N]]]:", defN_var)
        row += 1

        tk.Label(w, text="FIM Tokens", font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, padx=8, pady=(10, 4), sticky="w"
        )
        row += 1
        add_row(row, "fim_prefix:", fim_pref_var)
        row += 1
        add_row(row, "fim_suffix:", fim_suf_var)
        row += 1
        add_row(row, "fim_middle:", fim_mid_var)
        row += 1

        tk.Label(w, text="Theme", font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, padx=8, pady=(10, 4), sticky="w"
        )
        row += 1
        add_row(row, "Font family:", fontfam_var)
        row += 1
        add_row(row, "Font size:", fontsize_var)
        row += 1
        add_row(row, "Editor padding (px):", pad_var)
        row += 1

        def pick_fg():
            c = colorchooser.askcolor(color=fg_var.get(), title="Pick text color")
            if c and c[1]:
                fg_var.set(c[1])

        def pick_bg():
            c = colorchooser.askcolor(color=bg_var.get(), title="Pick background color")
            if c and c[1]:
                bg_var.set(c[1])

        tk.Label(w, text="Text color (hex):").grid(row=row, column=0, padx=8, pady=4, sticky="w")
        tk.Entry(w, textvariable=fg_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_fg).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        tk.Label(w, text="Background (hex):").grid(row=row, column=0, padx=8, pady=4, sticky="w")
        tk.Entry(w, textvariable=bg_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_bg).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        tk.Label(w, text="Spellcheck language (e.g., en_US):").grid(
            row=row, column=0, padx=8, pady=4, sticky="w"
        )
        tk.Entry(w, textvariable=spell_lang_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        row += 1

        def apply_and_close():
            try:
                self.cfg["endpoint"] = endpoint_var.get().strip().rstrip("/")
                self.cfg["model"] = model_var.get().strip()
                self.cfg["temperature"] = float(temp_var.get())
                self.cfg["top_p"] = float(top_p_var.get())
                self.cfg["default_n"] = max(1, min(4096, int(defN_var.get())))
                self.cfg["fim_prefix"] = fim_pref_var.get()
                self.cfg["fim_suffix"] = fim_suf_var.get()
                self.cfg["fim_middle"] = fim_mid_var.get()
                self.cfg["font_family"] = fontfam_var.get().strip() or DEFAULTS["font_family"]
                self.cfg["font_size"] = max(6, min(72, int(fontsize_var.get())))
                self.cfg["editor_padding_px"] = max(0, int(pad_var.get()))
                self.cfg["fg"] = fg_var.get().strip()
                self.cfg["bg"] = bg_var.get().strip()
                self.cfg["spell_lang"] = spell_lang_var.get().strip() or "en_US"
            except Exception as e:
                messagebox.showerror("Settings", f"Invalid value: {e}")
                return
            save_config(self.cfg)
            self._dictionary = self._load_dictionary(self.cfg["spell_lang"])
            self.app_font.config(family=self.cfg["font_family"], size=self.cfg["font_size"])
            for frame, st in self.tabs.items():
                t = st["text"]
                t.configure(
                    font=self.app_font,
                    fg=self.cfg["fg"],
                    bg=self.cfg["bg"],
                    insertbackground=self.cfg["fg"],
                )
                self._apply_editor_padding(t, self.cfg["editor_padding_px"])
                self._clear_line_spacing(t)
                # refresh spellcheck state
                if not self.cfg["spellcheck_enabled"]:
                    t.tag_remove("misspelled", "1.0", "end")
                else:
                    self._schedule_spellcheck_for_frame(frame, delay_ms=200)
            w.destroy()

        tk.Button(w, text="Save", command=apply_and_close).grid(
            row=row, column=1, padx=8, pady=12, sticky="e"
        )

    # ---------- Generate (streaming) ----------

    def _should_follow(self, text_widget: tk.Text) -> bool:
        try:
            _first, last = text_widget.yview()
        except Exception:
            return True
        return last >= 0.999

    def _reset_stream_state(self, st):
        job = st.get("stream_flush_job")
        if job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(job)
        st["stream_flush_job"] = None
        st["stream_buffer"].clear()
        st["stream_mark"] = None
        st["stream_following"] = False
        st["_stream_follow_primed"] = False
        st["stops_after"] = []
        st["stops_after_maxlen"] = 0
        st["stream_tail"] = ""
        st["stream_cancelled"] = False

    def _schedule_stream_flush(self, frame, mark):
        st = self.tabs.get(frame)
        if not st or st.get("stream_flush_job") is not None:
            return

        def _cb(fr=frame, mk=mark):
            st_inner = self.tabs.get(fr)
            if not st_inner:
                return
            st_inner["stream_flush_job"] = None
            self._flush_stream_buffer(fr, mk)

        st["stream_flush_job"] = self.after(20, _cb)

    def _flush_stream_buffer(self, frame, mark):
        st = self.tabs.get(frame)
        if not st:
            return
        if not st["stream_buffer"]:
            return

        text = st["text"]
        piece = "".join(st["stream_buffer"])
        st["stream_buffer"].clear()
        try:
            cur = text.index(mark)
        except tk.TclError:
            cur = text.index(tk.END)
        should_follow = st.get("stream_following", self._should_follow(text))
        text.insert(cur, piece)
        if should_follow:
            text.see(mark)
            primed = st.pop("_stream_follow_primed", False)
            if primed:
                st["stream_following"] = True
            else:
                try:
                    if text.dlineinfo(mark) is None:
                        st["stream_following"] = False
                        st["_stream_follow_primed"] = False
                    else:
                        st["stream_following"] = True
                        st["_stream_follow_primed"] = False
                except Exception:
                    st["stream_following"] = False
                    st["_stream_follow_primed"] = False
        elif self._should_follow(text):
            st["stream_following"] = True
            st["_stream_follow_primed"] = False
        self._set_dirty(st, True)

    def _force_flush_stream_buffer(self, frame, mark):
        st = self.tabs.get(frame)
        if not st:
            return
        job = st.get("stream_flush_job")
        if job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(job)
            st["stream_flush_job"] = None
        self._flush_stream_buffer(frame, mark)
        st["stream_mark"] = None

    def generate(self):
        st = self._current_tab_state()
        if not st:
            return

        text_widget = st["text"]
        cursor_index = text_widget.index(tk.INSERT)
        try:
            cursor_offset = int(text_widget.count("1.0", cursor_index, "chars")[0])
        except Exception:
            cursor_offset = None

        content = text_widget.get("1.0", tk.END)
        if cursor_offset is None:
            cursor_offset = len(content)
        cursor_offset = max(0, min(len(content), cursor_offset))

        fim_request = parse_fim_request(content, cursor_offset, self.cfg["default_n"])

        if fim_request is not None:
            self._launch_fim_or_completion_stream(st, content, fim_request)
            return

        messagebox.showinfo(
            "Generate",
            "Place the caret inside a [[[N]]] marker to generate.",
        )

    def _on_generate_shortcut(self, event):
        self.generate()
        return "break"

    def repeat_last_fim(self):
        st = self._current_tab_state()
        if not st:
            return

        text_widget = st.get("text")
        if text_widget is None:
            return

        marker = self._last_fim_marker or "[[[20]]]"

        try:
            start_index = text_widget.index(tk.INSERT)
        except tk.TclError:
            return

        try:
            text_widget.insert(start_index, marker)
        except tk.TclError:
            return

        marker_match = MARKER_REGEX.search(marker)
        if marker_match:
            body_offset = marker_match.start("body") - marker_match.start()
        else:
            body_offset = marker.find("]]]")
            if body_offset == -1:
                body_offset = len(marker)

        try:
            inside_index = text_widget.index(f"{start_index}+{body_offset}c")
        except tk.TclError:
            inside_index = text_widget.index(start_index)

        text_widget.mark_set(tk.INSERT, inside_index)
        text_widget.tag_remove("sel", "1.0", tk.END)
        text_widget.see(tk.INSERT)
        text_widget.focus_set()

        self.generate()

    def _on_repeat_last_fim_shortcut(self, event):
        self.repeat_last_fim()
        return "break"

    # ----- FIM/completion streaming -----

    def _launch_fim_or_completion_stream(self, st, content, fim_request: FIMRequest):
        cfg = self.cfg
        self._last_fim_marker = fim_request.marker.raw

        if fim_request.use_completion:
            prompt = fim_request.before_region
        else:
            prompt = (
                f"{cfg['fim_prefix']}{fim_request.before_region}{cfg['fim_suffix']}{fim_request.safe_suffix}{cfg['fim_middle']}"
            )

        payload = {
            "model": cfg["model"],
            "prompt": prompt,
            "max_tokens": fim_request.max_tokens,
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "stream": True,
        }
        if fim_request.stops_before:
            payload["stop"] = fim_request.stops_before

        text = st["text"]
        start_index = offset_to_tkindex(content, fim_request.marker.start)
        end_index = offset_to_tkindex(content, fim_request.marker.end)

        self._reset_stream_state(st)

        st["stops_after"] = fim_request.stops_after
        st["stops_after_maxlen"] = max((len(s) for s in fim_request.stops_after), default=0)
        st["stream_tail"] = ""
        st["stream_cancelled"] = False

        self._set_busy(True)

        # Prepare streaming mark
        text.mark_set("stream_here", start_index)
        text.mark_gravity("stream_here", tk.RIGHT)
        if fim_request.suffix_token is not None and not fim_request.keep_tags:
            s_s = offset_to_tkindex(content, fim_request.suffix_token.start)
            s_e = offset_to_tkindex(content, fim_request.suffix_token.end)
            with contextlib.suppress(tk.TclError):
                text.delete(s_s, s_e)
        if fim_request.prefix_token is not None and not fim_request.keep_tags:
            p_s = offset_to_tkindex(content, fim_request.prefix_token.start)
            p_e = offset_to_tkindex(content, fim_request.prefix_token.end)
            with contextlib.suppress(tk.TclError):
                text.delete(p_s, p_e)

        marker_len = fim_request.marker.end - fim_request.marker.start
        start_index = text.index("stream_here")
        end_index = text.index(f"{start_index}+{marker_len}c")
        text.delete(start_index, end_index)
        self._set_dirty(st, True)
        st["stream_mark"] = "stream_here"

        def worker(tab_id):
            try:
                for piece in stream_completion(cfg["endpoint"], payload):
                    self._result_queue.put(
                        {
                            "ok": True,
                            "kind": "stream_append",
                            "tab": tab_id,
                            "mark": "stream_here",
                            "text": piece,
                        }
                    )
            except Exception as e:
                self._result_queue.put({"ok": False, "error": str(e), "tab": tab_id})
            finally:
                # Always emit done; then kick spellcheck
                self._result_queue.put({"ok": True, "kind": "stream_done", "tab": tab_id})
                self._result_queue.put({"ok": True, "kind": "spellcheck_now", "tab": tab_id})

        threading.Thread(target=worker, args=(self.nb.select(),), daemon=True).start()

    # ---------- Queue handling ----------

    def _poll_queue(self):
        try:
            while True:
                item = self._result_queue.get_nowait()

                if not item.get("ok"):
                    tab_id = item.get("tab")
                    frame = self.nametowidget(tab_id) if tab_id else None
                    if frame in self.tabs:
                        st_err = self.tabs[frame]
                        mark = st_err.get("stream_mark") or "stream_here"
                        self._force_flush_stream_buffer(frame, mark)
                    self._set_busy(False)
                    messagebox.showerror("Generation Error", item.get("error", "Unknown error"))
                    continue

                kind = item.get("kind")
                tab_id = item.get("tab")
                frame = self.nametowidget(tab_id) if tab_id else None
                if not frame or frame not in self.tabs:
                    continue
                st = self.tabs[frame]
                text = st["text"]

                if kind == "stream_append":
                    if st.get("stream_cancelled") and not item.get("allow_stream_cancelled"):
                        continue

                    mark = item["mark"]
                    piece = item["text"]

                    if not item.get("allow_stream_cancelled"):
                        after_stops = st.get("stops_after", [])
                        if after_stops:
                            tail = st.get("stream_tail", "")
                            combined = tail + piece
                            match_index = None
                            match_stop = ""
                            for stop in after_stops:
                                idx = combined.find(stop)
                                if idx == -1:
                                    continue
                                if (
                                    match_index is None
                                    or idx < match_index
                                    or (idx == match_index and len(stop) > len(match_stop))
                                ):
                                    match_index = idx
                                    match_stop = stop

                            if match_index is not None:
                                pre_len = max(0, match_index - len(tail))
                                pre_piece = piece[:pre_len]
                                tail_overlap = max(0, len(tail) - match_index)
                                stop_remaining = match_stop[tail_overlap:]
                                if pre_piece:
                                    st["stream_buffer"].append(pre_piece)
                                if stop_remaining:
                                    st["stream_buffer"].append(stop_remaining)
                                st["stream_mark"] = mark
                                flush_mark = st.get("stream_mark") or "stream_here"
                                self._force_flush_stream_buffer(frame, flush_mark)
                                st["stream_cancelled"] = True
                                st["stops_after"] = []
                                st["stops_after_maxlen"] = 0
                                st["stream_tail"] = ""
                                self._result_queue.put(
                                    {"ok": True, "kind": "stream_done", "tab": tab_id}
                                )
                                self._result_queue.put(
                                    {"ok": True, "kind": "spellcheck_now", "tab": tab_id}
                                )
                                continue

                            maxlen = st.get("stops_after_maxlen", 0)
                            if maxlen > 0:
                                keep = maxlen - 1
                                st["stream_tail"] = combined[-keep:] if keep > 0 else ""
                            else:
                                st["stream_tail"] = ""
                        else:
                            st["stream_tail"] = ""
                    else:
                        st["stream_tail"] = ""

                    st["stream_buffer"].append(piece)
                    st["stream_mark"] = mark
                    self._schedule_stream_flush(frame, mark)

                elif kind == "stream_done":
                    mark = st.get("stream_mark") or item.get("mark") or "stream_here"
                    self._force_flush_stream_buffer(frame, mark)
                    st["stops_after"] = []
                    st["stops_after_maxlen"] = 0
                    st["stream_tail"] = ""
                    self._set_busy(False)

                elif kind == "spellcheck_now":
                    self._schedule_spellcheck_for_frame(frame, delay_ms=150)

                elif kind == "spell_result":
                    # Apply tag updates
                    text.tag_remove("misspelled", "1.0", "end")
                    for sidx, eidx in item.get("spans", []):
                        text.tag_add("misspelled", sidx, eidx)

                else:
                    pass

        except queue.Empty:
            pass

        self.after(60, self._poll_queue)

    # ---------- Spellcheck (enchant) ----------

    def _load_dictionary(self, lang: str):
        lang_code = lang or "en_US"
        try:
            self._spell_notice_msg = None
            self._spell_notice_last = None
            return enchant.Dict(lang_code)
        except enchant.errors.DictNotFoundError:
            self._spell_notice_msg = (
                f"Spellcheck unavailable: dictionary '{lang_code}' is not installed."
            )
            if lang_code != "en_US":
                with contextlib.suppress(enchant.errors.DictNotFoundError):
                    self._spell_notice_msg = None
                    self._spell_notice_last = None
                    return enchant.Dict("en_US")
            self._notify_spell_unavailable()
            return None
        except Exception:
            self._spell_notice_msg = "Spellcheck unavailable: failed to initialize dictionary."
            self._notify_spell_unavailable()
            return None

    def _notify_spell_unavailable(self):
        if not self._spell_notice_msg:
            return
        if self._spell_notice_msg == self._spell_notice_last:
            return
        with contextlib.suppress(Exception):
            messagebox.showwarning("Spellcheck", self._spell_notice_msg)
        self._spell_notice_last = self._spell_notice_msg

    def _schedule_spellcheck_for_frame(self, frame, delay_ms: int = 350):
        """
        Schedule a debounced spellcheck for the given tab/frame.
        Accepts either a ttk.Frame object or a Notebook tab-id string.
        """
        # Respect settings / availability
        dictionary = getattr(self, "_dictionary", None)
        if not self.cfg.get("spellcheck_enabled", True) or not dictionary:
            if not dictionary:
                notifier = getattr(self, "_notify_spell_unavailable", None)
                if callable(notifier):
                    notifier()
            if isinstance(frame, str):
                with contextlib.suppress(Exception):
                    frame = self.nametowidget(frame)
            if frame in self.tabs:
                st = self.tabs[frame]
                st["text"].tag_remove("misspelled", "1.0", "end")
                st["_spell_timer"] = None
            return

        # Normalize 'frame' if it's a tab-id string
        if isinstance(frame, str):
            try:
                frame = self.nametowidget(frame)
            except Exception:
                return  # invalid id

        if frame not in self.tabs:
            return

        st = self.tabs[frame]

        # cancel any pending timer for this tab
        tid = st.get("_spell_timer")
        if tid:
            with contextlib.suppress(Exception):
                self.after_cancel(tid)

        # schedule a new one
        st["_spell_timer"] = self.after(delay_ms, lambda fr=frame: self._spawn_spellcheck(fr))

    def _spawn_spellcheck(self, frame):
        dictionary = getattr(self, "_dictionary", None)
        if not self.cfg.get("spellcheck_enabled", True):
            notifier = getattr(self, "_notify_spell_unavailable", None)
            if callable(notifier):
                notifier()
            if frame in self.tabs:
                st = self.tabs[frame]
                st["text"].tag_remove("misspelled", "1.0", "end")
                st["_spell_timer"] = None
            return
        if not dictionary:
            notifier = getattr(self, "_notify_spell_unavailable", None)
            if callable(notifier):
                notifier()
        if frame not in self.tabs:
            return
        st = self.tabs[frame]
        t = st["text"]
        # Snapshot text (must be on main thread)
        txt = t.get("1.0", "end-1c")
        ignore = set(self._spell_ignore)  # copy
        dictionary = getattr(self, "_dictionary", None)

        def worker(tab_id, text_snapshot, ignore_set, dict_obj):
            try:
                # Extract words + offsets
                words = []
                offsets = []
                for m in WORD_RE.finditer(text_snapshot):
                    w = m.group(0)
                    if not w:
                        continue
                    words.append(w)
                    offsets.append((m.start(), m.end()))
                if not words:
                    self._result_queue.put(
                        {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                    )
                    return

                if dict_obj:
                    miss = set()
                    for w in set(words):
                        if not dict_obj.check(w):
                            miss.add(w)

                    miss = {w for w in miss if w not in ignore_set}

                    if not miss:
                        self._result_queue.put(
                            {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                        )
                        return

                    content = text_snapshot
                    out_spans = []
                    for w, (s_off, e_off) in zip(words, offsets, strict=False):
                        if w in miss:
                            sidx = offset_to_tkindex(content, s_off)
                            eidx = offset_to_tkindex(content, e_off)
                            out_spans.append((sidx, eidx))
                    self._result_queue.put(
                        {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": out_spans}
                    )
                    return

                # Fallback path for environments without dictionaries (used by tests)
                if not dict_obj:
                    lang = self.cfg.get("spell_lang", "en_US")
                    try:
                        proc = subprocess.run(  # noqa: UP022 - keep stdout/stderr for monkeypatch compat
                            ["aspell", "list", "-l", lang, "--encoding=utf-8"],
                            input="\n".join(words).encode("utf-8"),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=False,
                        )
                        miss_raw = proc.stdout.decode("utf-8", errors="ignore").splitlines()
                    except Exception:
                        miss_raw = []

                    miss = set(miss_raw) & set(words)
                    miss = {w for w in miss if w not in ignore_set}

                    if not miss:
                        self._result_queue.put(
                            {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                        )
                        return

                    content = text_snapshot
                    out_spans = []
                    for w, (s_off, e_off) in zip(words, offsets, strict=False):
                        if w in miss:
                            sidx = offset_to_tkindex(content, s_off)
                            eidx = offset_to_tkindex(content, e_off)
                            out_spans.append((sidx, eidx))
                    self._result_queue.put(
                        {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": out_spans}
                    )
                    return
            except Exception:
                # swallow spell errors silently
                self._result_queue.put(
                    {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                )

        threading.Thread(
            target=worker, args=(self.nb.select(), txt, ignore, dictionary), daemon=True
        ).start()

    def _spell_context_menu(self, event, frame):
        if not self.cfg.get("spellcheck_enabled", True) or not self._dictionary:
            return
        if frame not in self.tabs:
            return
        st = self.tabs[frame]
        t = st["text"]

        # Index under mouse
        idx = t.index(f"@{event.x},{event.y}")
        # Bias inside character so tag lookup works at word start
        idx_inside = t.index(f"{idx}+1c")

        # Find the misspelled tag range that contains idx_inside
        hit_start = hit_end = None
        ranges = list(
            zip(t.tag_ranges("misspelled")[0::2], t.tag_ranges("misspelled")[1::2], strict=False)
        )
        for s, e in ranges:
            if t.compare(idx_inside, ">=", s) and t.compare(idx_inside, "<", e):
                hit_start, hit_end = s, e
                break
        if not hit_start:
            return  # not on a misspelled word

        word = t.get(hit_start, hit_end).strip()
        if not word:
            return

        menu = tk.Menu(t, tearoff=0)
        temp_bindings = []

        def remove_temp_bindings():
            nonlocal temp_bindings
            for sequence, funcid in temp_bindings:
                if funcid:
                    self.unbind(sequence, funcid)
            temp_bindings = []

        def close_menu(event=None):
            remove_temp_bindings()
            with contextlib.suppress(tk.TclError):
                menu.unpost()

        def bind_temp(sequence, func, add="+"):
            funcid = self.bind(sequence, func, add=add)
            temp_bindings.append((sequence, funcid))

        def handle_click(event):
            if menu.winfo_ismapped():
                mx, my = menu.winfo_rootx(), menu.winfo_rooty()
                mw, mh = mx + menu.winfo_width(), my + menu.winfo_height()
                if mx <= event.x_root < mw and my <= event.y_root < mh:
                    return
            close_menu()

        def handle_escape(event):
            close_menu()
            return "break"

        bind_temp("<Button-1>", handle_click)
        bind_temp("<Button-2>", handle_click)
        bind_temp("<Escape>", handle_escape)
        menu.bind("<Unmap>", lambda e: remove_temp_bindings(), add="+")

        suggs = self._spell_suggestions(word)
        if suggs:
            for s in suggs[:8]:
                menu.add_command(
                    label=s,
                    command=lambda s=s, sidx=hit_start, eidx=hit_end: self._replace_range(
                        t, sidx, eidx, s
                    ),
                )
            menu.add_separator()
        menu.add_command(
            label=f"Ignore '{word}' (session)", command=lambda w=word: self._ignore_word_session(w)
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _ignore_word_session(self, word):
        self._spell_ignore.add(word)
        # re-run spellcheck on current tab
        frame = self.nb.select()
        self._schedule_spellcheck_for_frame(frame, delay_ms=50)

    def _replace_range(self, t, sidx, eidx, text):
        t.delete(sidx, eidx)
        t.insert(sidx, text)

    def _spell_suggestions(self, word):
        dictionary = self._dictionary
        if not dictionary:
            return []
        try:
            if dictionary.check(word):
                return []
            return dictionary.suggest(word)
        except Exception:
            return []

    # ---------- Utils ----------

    def _set_busy(self, busy: bool):
        self.config(cursor="watch" if busy else "")
        self.update_idletasks()

    # ---------- Close / Quit ----------

    def _on_close(self):
        for frame, st in list(self.tabs.items()):
            if st.get("dirty"):
                self.nb.select(frame)
                if not self._maybe_save(st):
                    return
        save_config(self.cfg)
        self.destroy()


def main():
    app = FIMPad()
    app.mainloop()


if __name__ == "__main__":
    main()
