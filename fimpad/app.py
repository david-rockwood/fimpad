#!/usr/bin/env python3
"""
FIMpad — Tabbed Tkinter editor for llama-server
with FIM streaming, dirty tracking, and enchant-based spellcheck.
"""

import contextlib
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from importlib import resources
from importlib.resources.abc import Traversable
from tkinter import colorchooser, filedialog, messagebox, ttk

import enchant

from .client import stream_completion
from .config import DEFAULTS, WORD_RE, load_config, save_config
from .library_resources import iter_library
from .parser import (
    FIMRequest,
    FIMTag,
    PrefixSuffixTag,
    SequenceTag,
    TagParseError,
    TagToken,
    cursor_within_span,
    parse_fim_request,
    parse_triple_tokens,
)
from .stream_utils import find_stream_match
from .utils import offset_to_tkindex


class FIMPad(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FIMpad")
        self.geometry("1100x750")

        self.cfg = load_config()
        self.app_font = tkfont.Font(family=self.cfg["font_family"], size=self.cfg["font_size"])

        self._apply_open_maximized(self.cfg.get("open_maximized", False))

        try:
            self.style = ttk.Style(self)
            if "clam" in self.style.theme_names():
                self.style.theme_use("clam")
        except Exception:
            pass

        self._library = iter_library()
        self._spell_menu_var: tk.BooleanVar | None = None
        self._wrap_menu_var: tk.BooleanVar | None = None
        self._follow_menu_var: tk.BooleanVar | None = None
        self._line_numbers_menu_var: tk.BooleanVar | None = None
        self._build_menu()
        self._build_notebook()
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._result_queue = queue.Queue()
        self.after(60, self._poll_queue)

        self._spell_notice_msg: str | None = None
        self._spell_notice_last: str | None = None
        self._available_spell_langs = self._list_spell_languages()
        self._spell_lang = self._determine_spell_language(
            self.cfg.get("spell_lang")
        )
        self._dictionary = self._load_dictionary(self._spell_lang)
        self._spell_ignore = set()  # session-level ignores

        self._fim_log: list[dict[str, str]] = []

        self._last_fim_marker: str | None = None
        self._last_tab: str | None = None
        self._fim_generation_active: bool = False
        self._sequence_queue: list[str] = []
        self._sequence_tab: str | None = None
        self._sequence_names: tuple[str, ...] | None = None

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
        self.bind_all("<Control-Alt-Return>", self._on_paste_last_fim_tag_shortcut)
        self.bind_all("<Control-Alt-KP_Enter>", self._on_paste_last_fim_tag_shortcut)
        self.bind_all("<Control-l>", self._on_show_fim_log_shortcut)
        self.bind_all("<Control-f>", lambda e: self._open_replace_dialog())
        self.bind_all("<Control-r>", lambda e: self._open_regex_replace_dialog())
        self.bind_all("<Control-Escape>", self._on_interrupt_stream)
        self.bind_all("<Control-w>", lambda e: self._close_current_tab())  # close tab
        self.bind_all("<Alt-z>", lambda e: self._toggle_wrap_current())  # wrap toggle
        self.bind_all("<Alt-f>", lambda e: self._toggle_follow_stream())  # follow toggle
        self.bind_all("<Alt-s>", lambda e: self._toggle_spellcheck())  # spell toggle
        self.bind_all("<Alt-n>", lambda e: self._toggle_line_numbers())  # line numbers
        self.bind_all("<Control-a>", lambda e: self._select_all_current())  # select all
        self.bind_all("<Control-t>", lambda e: self._open_settings())

        for idx in range(1, 10):
            self.bind_all(
                f"<Alt-Key-{idx}>",
                lambda e, index=idx - 1: self._select_tab_by_index(index),
            )
        self.bind_all("<Alt-Key-0>", lambda e: self._select_tab_by_index(9))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_window(self, window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
        parent_widget = parent or window.master or self
        try:
            parent_widget = parent_widget.winfo_toplevel()
            window.update_idletasks()
            parent_x = parent_widget.winfo_rootx()
            parent_y = parent_widget.winfo_rooty()
            parent_w = parent_widget.winfo_width()
            parent_h = parent_widget.winfo_height()
            win_w = window.winfo_width()
            win_h = window.winfo_height()
            x = parent_x + max(0, (parent_w - win_w) // 2)
            y = parent_y + max(0, (parent_h - win_h) // 2)
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _apply_open_maximized(self, open_maximized: bool) -> None:
        with contextlib.suppress(tk.TclError):
            if open_maximized:
                try:
                    self.state("zoomed")
                except tk.TclError:
                    self.attributes("-zoomed", True)
            else:
                try:
                    self.state("normal")
                except tk.TclError:
                    self.attributes("-zoomed", False)

    def _lift_if_exists(self, widget: tk.Misc) -> None:
        with contextlib.suppress(tk.TclError):
            if widget.winfo_exists():
                widget.lift()

    def _prepare_child_window(self, window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
        parent_widget = parent or window.master or self
        with contextlib.suppress(tk.TclError):
            parent_widget = parent_widget.winfo_toplevel()
            window.transient(parent_widget)
            window.lift(parent_widget)
            self._lift_if_exists(parent_widget)
            parent_widget.bind(
                "<FocusIn>",
                lambda _e, w=window: self._lift_if_exists(w),
                add="+",
            )
        window.bind("<FocusIn>", lambda e: self._lift_if_exists(e.widget), add="+")
        self._center_window(window, parent_widget)

    def _configure_find_highlight(self, text: tk.Text, tag: str = "find_replace_match") -> None:
        text.tag_configure(
            tag,
            background=self.cfg["highlight2"],
            foreground=self.cfg["bg"],
        )

    # ---------- Notebook / Tabs ----------

    def _build_notebook(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)
        self.nb.enable_traversal()
        self.tabs = {}  # frame -> state dict
        self._tab_close_image: tk.PhotoImage | None = None
        self._tab_close_image_active: tk.PhotoImage | None = None
        self._tab_close_support: str | None = None
        self._tab_close_hit_padding = 6
        self._tab_close_compound_padding = (8, 4, 16, 4)
        self._tab_close_hover_tab: str | None = None
        self._setup_closable_tabs()

    def _setup_closable_tabs(self) -> None:
        self._tab_close_image = self._create_close_image(
            fill="#555555", size=16, margin=3, stroke=2
        )
        self._tab_close_image_active = self._create_close_image(
            fill="#cc3333", size=16, margin=3, stroke=2
        )

        style = getattr(self, "style", None) or ttk.Style(self)

        try:
            style.element_create(
                "Notebook.close",
                "image",
                self._tab_close_image,
                ("active", self._tab_close_image_active),
                border=0,
                sticky="",
            )
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
                                                            },
                                                        ),
                                                        (
                                                            "Notebook.close",
                                                            {
                                                                "side": "right",
                                                                "sticky": "",
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
            style.configure(
                "ClosableNotebook.TNotebook.Tab", padding=(8, 4, 16, 4)
            )
            self.nb.configure(style="ClosableNotebook.TNotebook")
            self.nb.bind("<Button-1>", self._handle_tab_close_click, add="+")
            self._tab_close_support = "element"
            return
        except tk.TclError:
            pass

        self._tab_close_support = "compound"
        self.nb.bind("<Button-1>", self._handle_tab_close_click, add="+")
        self.nb.bind("<Motion>", self._handle_tab_motion, add="+")
        self.nb.bind("<Leave>", lambda e: self._set_close_hover_tab(None), add="+")

    def _create_close_image(
        self, fill: str, size: int = 12, margin: int = 2, stroke: int = 2
    ) -> tk.PhotoImage:
        image = tk.PhotoImage(width=size, height=size)
        radius = max(0, stroke // 2)

        def paint(px: int, py: int) -> None:
            if 0 <= px < size and 0 <= py < size:
                image.put(fill, (px, py))

        for i in range(margin, size - margin):
            tl_br = (i, i)
            bl_tr = (i, size - i - 1)
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    paint(tl_br[0] + dx, tl_br[1] + dy)
                    paint(bl_tr[0] + dx, bl_tr[1] + dy)
        return image

    def _apply_tab_title(self, tab_id, title: str) -> None:
        if self._tab_close_support == "compound":
            if not tab_id:
                return
            image = (
                self._tab_close_image_active
                if tab_id == self._tab_close_hover_tab
                else self._tab_close_image
            )
            kwargs = {
                "text": title,
                "compound": tk.RIGHT,
                "padding": self._tab_close_compound_padding,
            }
            if image is not None:
                kwargs["image"] = image
            self.nb.tab(tab_id, **kwargs)
        else:
            self.nb.tab(tab_id, text=title)

    def _identify_tab_index_at(self, x: int, y: int) -> int | None:
        try:
            index = self.nb.tk.call(self.nb._w, "identify", "tab", x, y)
        except tk.TclError:
            return None
        try:
            index = int(index)
        except (TypeError, ValueError):
            return None
        tabs = self.nb.tabs()
        if index < 0 or index >= len(tabs):
            return None
        return index

    def _identify_tab_element(self, x: int, y: int) -> str:
        try:
            element = self.nb.tk.call(self.nb._w, "identify", "element", x, y)
        except tk.TclError:
            return ""
        if not element:
            return ""
        parts = str(element).split("!")[-1].split(".")
        return parts[-1].lower() if parts else ""

    def _is_fallback_close_hit(self, x: int, y: int, tab_id: str, debug: bool = False) -> bool:
        if self._tab_close_support != "compound":
            return False
        try:
            tab_index = self.nb.index(tab_id)
            bbox = self.nb.bbox(tab_index)
        except tk.TclError:
            return False
        if not bbox:
            return False
        tab_x, tab_y, width, height = bbox
        image_width = self._tab_close_image.width() if self._tab_close_image else 0
        right_pad = self._tab_close_compound_padding[2] if self._tab_close_compound_padding else 0
        button_right = tab_x + width - right_pad
        button_left = button_right - image_width
        hit_pad = self._tab_close_hit_padding or 0
        if x < button_left - hit_pad or x > button_right + hit_pad:
            return False
        return not (y < tab_y or y > tab_y + height)

    def _handle_tab_close_click(self, event) -> None:
        if self._tab_close_support not in {"element", "compound"}:
            return
        index = self._identify_tab_index_at(event.x, event.y)
        if index is None:
            return
        tabs = self.nb.tabs()
        if index >= len(tabs):
            return
        tab_id = tabs[index]
        if self._tab_close_support == "element":
            element = self._identify_tab_element(event.x, event.y)
            if "close" not in element:
                return
        elif self._tab_close_support == "compound":
            if not self._is_fallback_close_hit(event.x, event.y, tab_id):
                return
            self._set_close_hover_tab(None)
        self.nb.select(tab_id)
        self._close_current_tab()

    def _handle_tab_motion(self, event) -> None:
        if self._tab_close_support != "compound":
            return
        index = self._identify_tab_index_at(event.x, event.y)
        if index is None:
            self._set_close_hover_tab(None)
            return
        tabs = self.nb.tabs()
        if index >= len(tabs):
            self._set_close_hover_tab(None)
            return
        tab_id = tabs[index]
        if self._is_fallback_close_hit(event.x, event.y, tab_id):
            self._set_close_hover_tab(tab_id)
        else:
            self._set_close_hover_tab(None)

    def _set_close_hover_tab(self, tab_id: str | None) -> None:
        if self._tab_close_support != "compound":
            return
        if tab_id == self._tab_close_hover_tab:
            return
        prev = self._tab_close_hover_tab
        self._tab_close_hover_tab = tab_id
        for target in filter(None, (prev, tab_id)):
            try:
                title = self.nb.tab(target, option="text")
            except tk.TclError:
                continue
            self._apply_tab_title(target, title)

    def _new_tab(self, content: str = "", title: str = "Untitled"):
        frame = ttk.Frame(self.nb)
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        content_frame = tk.Frame(
            text_frame, bg=self.cfg["bg"], borderwidth=0, highlightthickness=0
        )
        content_frame.grid(row=0, column=0, sticky="nsew")
        content_frame.grid_columnconfigure(3, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        left_padding = tk.Frame(
            content_frame,
            width=self.cfg["editor_padding_px"],
            bg=self.cfg["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        left_padding.grid(row=0, column=0, sticky="ns")

        line_numbers = tk.Canvas(
            content_frame,
            width=0,
            highlightthickness=0,
            bd=0,
            bg=self.cfg["highlight2"],
            takefocus=0,
        )
        line_numbers.grid(row=0, column=1, sticky="ns")
        for sequence in ("<Button-1>", "<Double-Button-1>", "<B1-Motion>"):
            line_numbers.bind(sequence, lambda e: "break")

        gutter_gap = tk.Frame(
            content_frame,
            width=self.cfg.get("line_number_padding_px", DEFAULTS["line_number_padding_px"]),
            bg=self.cfg["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        gutter_gap.grid(row=0, column=2, sticky="ns")

        text = tk.Text(
            content_frame,
            undo=True,
            maxundo=-1,
            wrap=tk.WORD,
            highlightthickness=0,
            borderwidth=0,
            relief=tk.FLAT,
            yscrollcommand=lambda f1, f2, fr=frame: self._on_text_scroll(fr, f1, f2),
        )
        text.grid(row=0, column=3, sticky="nsew")

        right_padding = tk.Frame(
            content_frame,
            width=self.cfg["editor_padding_px"],
            bg=self.cfg["bg"],
            borderwidth=0,
            highlightthickness=0,
        )
        right_padding.grid(row=0, column=4, sticky="ns")

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        scrollbar.grid(row=0, column=1, sticky="ns")
        scrollbar.config(command=lambda *args, fr=frame: self._on_scrollbar_scroll(fr, *args))
        text.configure(
            font=self.app_font,
            fg=self.cfg["fg"],
            bg=self.cfg["bg"],
            insertbackground=self.cfg["highlight1"],
            selectbackground=self.cfg["highlight2"],
            selectforeground=self.cfg["bg"],
        )
        self._configure_find_highlight(text)
        st = {
            "frame": frame,
            "path": None,
            "text": text,
            "line_numbers": line_numbers,
            "content_frame": content_frame,
            "left_padding": left_padding,
            "right_padding": right_padding,
            "gutter_gap": gutter_gap,
            "scrollbar": scrollbar,
            "wrap": "word",  # "word" or "none"
            "dirty": False,
            "suppress_modified": False,
            "_spell_timer": None,
            "stream_buffer": [],
            "stream_flush_job": None,
            "stream_mark": None,
            "stream_following": False,
            "_stream_follow_primed": False,
            "stream_patterns": [],
            "stream_accumulated": "",
            "stream_cancelled": False,
            "stream_stop_event": None,
            "post_actions": [],
            "last_insert": "1.0",
            "last_yview": 0.0,
            "line_numbers_enabled": self.cfg.get("line_numbers_enabled", False),
            "_line_number_job": None,
        }

        self._apply_editor_padding(st, self.cfg["editor_padding_px"])
        self._apply_line_number_padding(
            st, self.cfg.get("line_number_padding_px", DEFAULTS["line_number_padding_px"])
        )
        self._clear_line_spacing(text)
        self._bind_scroll_events(frame, text, line_numbers, gutter_gap, content_frame)

        # Spellcheck tag + bindings
        text.tag_configure(
            "misspelled", underline=True, foreground=self.cfg["highlight1"]
        )
        text.bind(
            "<Button-3>", lambda e, fr=frame: self._spell_context_menu(e, fr)
        )  # right-click menu
        text.bind("<KeyRelease>", lambda e, fr=frame: self._schedule_spellcheck_for_frame(fr))
        text.bind("<Configure>", lambda e, fr=frame: self._schedule_line_number_update(fr))
        text.bind("<Control-Return>", self._on_generate_shortcut)
        text.bind("<Control-KP_Enter>", self._on_generate_shortcut)
        text.bind("<Control-Shift-Return>", self._on_repeat_last_fim_shortcut)
        text.bind("<Control-Shift-KP_Enter>", self._on_repeat_last_fim_shortcut)
        text.bind("<Control-Alt-Return>", self._on_paste_last_fim_tag_shortcut)
        text.bind("<Control-Alt-KP_Enter>", self._on_paste_last_fim_tag_shortcut)
        text.bind("<<Paste>>", self._on_text_paste, add="+")
        text.bind("<Home>", self._on_home_key)
        text.bind("<End>", self._on_end_key)
        text.bind("<Control-Home>", self._on_ctrl_home_key)
        text.bind("<Control-End>", self._on_ctrl_end_key)

        def on_modified(event=None):
            if st["suppress_modified"]:
                text.edit_modified(False)
            elif text.edit_modified():
                self._set_dirty(st, True)
                text.edit_modified(False)
            self._schedule_line_number_update(frame)

        text.bind("<<Modified>>", on_modified)

        st["suppress_modified"] = True
        text.insert("1.0", content)
        text.edit_modified(False)
        st["suppress_modified"] = False

        self.tabs[frame] = st
        self.nb.add(frame, text=title)
        self._apply_tab_title(frame, title)
        self.nb.select(frame)

        if self._last_tab is None:
            self._last_tab = self.nb.select()

        text.focus_set()
        text.mark_set("insert", "1.0")
        text.see("1.0")

        self._apply_line_numbers_state(st, st["line_numbers_enabled"])

        # Initial spellcheck (debounced)
        self._schedule_spellcheck_for_frame(frame, delay_ms=250)
        self._sync_wrap_menu_var()
        self._sync_line_numbers_menu_var()
        self._schedule_line_number_update(frame, delay_ms=10)

    def _on_tab_changed(self, event=None):
        previous = self._last_tab
        if previous:
            self._store_tab_view(previous)

        current = self.nb.select()
        if current:
            self._restore_tab_view(current)
            self._schedule_spellcheck_for_frame(current, delay_ms=80)
            self._schedule_line_number_update(current, delay_ms=10)

        self._last_tab = current
        self._sync_wrap_menu_var()
        self._sync_line_numbers_menu_var()

    def _store_tab_view(self, tab_id: str) -> None:
        try:
            frame = self.nametowidget(tab_id)
        except Exception:
            return
        st = self.tabs.get(frame)
        if not st:
            return
        text: tk.Text | None = st.get("text")
        if not text:
            return
        st["last_insert"] = text.index("insert")
        st["last_yview"] = text.yview()[0]

    def _restore_tab_view(self, tab_id: str) -> None:
        try:
            frame = self.nametowidget(tab_id)
        except Exception:
            return
        st = self.tabs.get(frame)
        if not st:
            return
        text: tk.Text | None = st.get("text")
        if not text:
            return
        insert_idx = st.get("last_insert", "1.0")
        yview = st.get("last_yview", 0.0)
        text.mark_set("insert", insert_idx)
        with contextlib.suppress(Exception):
            text.yview_moveto(yview)
        text.see("insert")
        text.focus_set()
        self._schedule_line_number_update(frame, delay_ms=10)

    def _log_fim_generation(self, fim_request: FIMRequest) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        if fim_request.use_completion:
            prefix_text = fim_request.before_region
            suffix_text = fim_request.safe_suffix
        else:
            prefix_text = f"{self.cfg['fim_prefix']}{fim_request.before_region}"
            suffix_text = (
                f"{self.cfg['fim_suffix']}{fim_request.safe_suffix}{self.cfg['fim_middle']}"
            )

        self._fim_log.append(
            {"time": timestamp, "prefix": prefix_text, "suffix": suffix_text}
        )

    def _open_fim_log_tab(self) -> None:
        if not self._fim_log:
            log_body = "FIM Generation Log is empty.\n"
        else:
            lines = ["FIM Generation Log", ""]
            for entry in self._fim_log:
                lines.append(f"[{entry['time']}]")
                lines.append("Prefix:")
                lines.append(entry["prefix"])
                lines.append("Suffix:")
                lines.append(entry["suffix"])
                lines.append("")
            log_body = "\n".join(lines).rstrip() + "\n"

        self._new_tab(content=log_body, title="FIM Log")

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
        title = self._format_tab_title(st)
        self._apply_tab_title(tab, title)

    def _format_tab_title(self, st: dict) -> str:
        path = st.get("path")
        title = os.path.basename(path) if path else "Untitled"
        if st.get("dirty"):
            title = f"• {title}"
        return title

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
        if (
            self._tab_close_support == "compound"
            and cur
            and cur == self._tab_close_hover_tab
        ):
            self._set_close_hover_tab(None)
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
        editmenu.add_command(
            label="Cut",
            accelerator="Ctrl+X",
            command=lambda: self._cur_text().event_generate("<<Cut>>"),
        )
        editmenu.add_command(
            label="Copy",
            accelerator="Ctrl+C",
            command=lambda: self._cur_text().event_generate("<<Copy>>"),
        )
        editmenu.add_command(
            label="Paste",
            accelerator="Ctrl+V",
            command=lambda: self._cur_text().event_generate("<<Paste>>"),
        )
        editmenu.add_command(
            label="Delete",
            accelerator="Del",
            command=lambda: self._cur_text().event_generate("<<Clear>>"),
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Select All", accelerator="Ctrl+A", command=self._select_all_current
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Find & Replace…", accelerator="Ctrl+F", command=self._open_replace_dialog
        )
        editmenu.add_command(
            label="Regex & Replace…", accelerator="Ctrl+R", command=self._open_regex_replace_dialog
        )
        editmenu.add_separator()
        self._wrap_menu_var = tk.BooleanVar(value=True)
        editmenu.add_checkbutton(
            label="Toggle Wrap",
            accelerator="Alt+Z",
            variable=self._wrap_menu_var,
            command=self._on_wrap_menu_toggled,
        )
        self._follow_menu_var = tk.BooleanVar(
            value=self.cfg.get("follow_stream_enabled", True)
        )
        editmenu.add_checkbutton(
            label="Toggle Follow",
            accelerator="Alt+F",
            variable=self._follow_menu_var,
            command=self._on_follow_menu_toggled,
        )
        self._line_numbers_menu_var = tk.BooleanVar(
            value=self.cfg.get("line_numbers_enabled", False)
        )
        editmenu.add_checkbutton(
            label="Toggle Line Numbers",
            accelerator="Alt+N",
            variable=self._line_numbers_menu_var,
            command=self._toggle_line_numbers,
        )
        self._spell_menu_var = tk.BooleanVar(value=self.cfg.get("spellcheck_enabled", True))
        editmenu.add_checkbutton(
            label="Toggle Spellcheck",
            accelerator="Alt+S",
            variable=self._spell_menu_var,
            command=self._toggle_spellcheck,
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
        aimenu.add_command(
            label="Paste Last FIM Tag",
            accelerator="Ctrl+Alt+Enter",
            command=self.paste_last_fim_tag,
        )
        aimenu.add_command(
            label="Interrupt Stream",
            accelerator="Ctrl+Esc",
            command=self.interrupt_stream,
        )
        menubar.add_cascade(label="AI", menu=aimenu)

        library_menu = tk.Menu(menubar, tearoff=0)
        if not self._library:
            library_menu.add_command(label="(No library files found)", state="disabled")
        else:
            top_level_items = self._library.get(None, [])
            for title, resource in top_level_items:
                library_menu.add_command(
                    label=title,
                    command=lambda t=title, r=resource: self._open_library_resource(t, r),
                )

            for group, entries in self._library.items():
                if group is None:
                    continue
                submenu = tk.Menu(library_menu, tearoff=0)
                for title, resource in entries:
                    submenu.add_command(
                        label=title,
                        command=lambda t=title, r=resource: self._open_library_resource(
                            t, r
                        ),
                    )
                library_menu.add_cascade(label=group, menu=submenu)
        menubar.add_cascade(label="Library", menu=library_menu)

        self.config(menu=menubar)

    # ---------- Helpers ----------

    def _apply_editor_padding(self, st: dict, pad_px: int) -> None:
        pad_px = max(0, int(pad_px))
        st["text"].configure(padx=0, pady=0)
        for key in ("left_padding", "right_padding"):
            pad = st.get(key)
            if pad is not None:
                pad.configure(width=pad_px, bg=self.cfg["bg"], highlightthickness=0, bd=0)

    def _apply_line_number_padding(self, st: dict, pad_px: int) -> None:
        pad_px = max(0, int(pad_px))
        gap = st.get("gutter_gap")
        if gap is not None:
            gap.configure(width=pad_px, bg=self.cfg["bg"], highlightthickness=0, bd=0)

    def _reflow_text_layout(self, st: dict) -> None:
        text: tk.Text | None = st.get("text")
        if text is None:
            return

        try:
            insert_index = text.index("insert")
        except tk.TclError:
            insert_index = None

        try:
            yview = text.yview()[0]
        except Exception:
            yview = None

        wrap_value = text.cget("wrap")
        temp_wrap = tk.CHAR if wrap_value == tk.WORD else tk.WORD

        try:
            text.configure(wrap=temp_wrap)
            text.update_idletasks()
        finally:
            text.configure(wrap=wrap_value)

        if insert_index is not None:
            with contextlib.suppress(tk.TclError):
                text.mark_set("insert", insert_index)

        if yview is not None:
            with contextlib.suppress(Exception):
                text.yview_moveto(yview)

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

    def _bind_scroll_events(
        self,
        frame,
        text: tk.Text,
        line_numbers: tk.Canvas,
        gutter_gap: tk.Frame,
        content_frame: tk.Frame,
    ) -> None:
        widgets = (text, line_numbers, gutter_gap, content_frame)
        for widget in widgets:
            widget.bind(
                "<MouseWheel>",
                lambda e, fr=frame: self._on_mousewheel(fr, e),
                add="+",
            )
            widget.bind(
                "<Button-4>",
                lambda e, fr=frame: self._on_mousewheel(fr, e),
                add="+",
            )
            widget.bind(
                "<Button-5>",
                lambda e, fr=frame: self._on_mousewheel(fr, e),
                add="+",
            )

    def _on_mousewheel(self, frame, event) -> str | None:
        st = self.tabs.get(frame)
        if not st:
            return None

        multiplier = max(1, int(self.cfg.get("scroll_speed_multiplier", 1)))
        direction = 0
        if getattr(event, "delta", 0):
            direction = -1 if event.delta > 0 else 1
        elif getattr(event, "num", None) in (4, 5):
            direction = -1 if event.num == 4 else 1

        if direction == 0:
            return None

        st["text"].yview_scroll(direction * multiplier, "units")
        self._schedule_line_number_update(frame, delay_ms=10)
        return "break"

    def _on_text_scroll(self, frame, first: str, last: str) -> None:
        st = self.tabs.get(frame)
        if not st:
            return
        scrollbar: ttk.Scrollbar | None = st.get("scrollbar")
        if scrollbar:
            scrollbar.set(first, last)
        self._schedule_line_number_update(frame, delay_ms=10)
        scroll_delay = int(
            self.cfg.get(
                "spellcheck_scroll_debounce_ms",
                DEFAULTS["spellcheck_scroll_debounce_ms"],
            )
        )
        self._schedule_spellcheck_for_frame(frame, delay_ms=scroll_delay)

    def _on_scrollbar_scroll(self, frame, *args) -> None:
        st = self.tabs.get(frame)
        if not st:
            return
        st["text"].yview(*args)
        self._schedule_line_number_update(frame, delay_ms=10)

    def _schedule_line_number_update(self, frame, delay_ms: int = 30) -> None:
        st = self.tabs.get(frame)
        if not st:
            return
        job = st.get("_line_number_job")
        if job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(job)
        st["_line_number_job"] = self.after(delay_ms, lambda fr=frame: self._draw_line_numbers(fr))

    def _draw_line_numbers(self, frame) -> None:
        st = self.tabs.get(frame)
        if not st:
            return
        st["_line_number_job"] = None
        self._render_line_numbers(st)

    def _render_line_numbers(self, st: dict) -> None:
        text: tk.Text = st["text"]
        canvas: tk.Canvas = st["line_numbers"]
        if not st.get("line_numbers_enabled", False):
            canvas.configure(width=0)
            canvas.grid_remove()
            canvas.delete("all")
            return

        canvas.grid()

        if not text.winfo_ismapped():
            return

        total_lines = max(1, int(text.index("end-1c").split(".")[0]))
        digits = max(2, len(str(total_lines)))
        number_width = self.app_font.measure("9" * digits)
        gutter_width = number_width + 6
        canvas_width = gutter_width
        canvas.configure(
            width=canvas_width,
            bg=self.cfg["bg"],
            highlightthickness=0,
            bd=0,
        )
        canvas.delete("all")

        visible_height = text.winfo_height()
        canvas.create_rectangle(
            max(0, canvas_width - gutter_width),
            0,
            canvas_width,
            visible_height,
            outline="",
            fill=self.cfg["highlight2"],
        )
        index = text.index("@0,0")
        visited = set()
        while True:
            if index in visited:
                break
            visited.add(index)
            dline = text.dlineinfo(index)
            if dline is None:
                break
            y_px = dline[1]
            line_height = dline[3]
            if y_px > visible_height + line_height:
                break
            line_no = int(index.split(".")[0])
            is_line_start = text.compare(index, "==", f"{line_no}.0")
            label = (str(line_no) if is_line_start else "".rjust(digits))
            canvas.create_text(
                canvas_width - 3,
                y_px,
                anchor="ne",
                text=label,
                font=self.app_font,
                fill=self.cfg["highlight1"],
            )

            try:
                next_index = text.index(f"{index}+1displayline")
            except tk.TclError:
                break
            if text.compare(next_index, "<=", index):
                break
            if text.compare(next_index, ">", "end-1c"):
                break
            index = next_index

    def _apply_line_numbers_state(self, st: dict, enabled: bool) -> None:
        st["line_numbers_enabled"] = enabled
        self._render_line_numbers(st)

    def _sync_line_numbers_menu_var(self) -> None:
        if self._line_numbers_menu_var is None:
            return
        self._line_numbers_menu_var.set(self.cfg.get("line_numbers_enabled", False))

    def _cur_text(self) -> tk.Text:
        st = self._current_tab_state()
        return st["text"]

    def _on_text_paste(self, event: tk.Event) -> None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Text):
            return

        try:
            sel_first = widget.index("sel.first")
            sel_last = widget.index("sel.last")
        except tk.TclError:
            return

        widget.mark_set(tk.INSERT, sel_first)
        widget.delete(sel_first, sel_last)

    def _on_home_key(self, event: tk.Event) -> str | None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Text):
            return None

        target_index = widget.index("insert linestart")
        widget.mark_set(tk.INSERT, target_index)
        widget.see(target_index)
        return "break"

    def _on_ctrl_home_key(self, event: tk.Event) -> str | None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Text):
            return None

        widget.mark_set(tk.INSERT, "1.0")
        widget.see("1.0")
        return "break"

    def _on_end_key(self, event: tk.Event) -> str | None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Text):
            return None

        target_index = widget.index("insert lineend")
        widget.mark_set(tk.INSERT, target_index)
        widget.see(target_index)
        return "break"

    def _on_ctrl_end_key(self, event: tk.Event) -> str | None:
        widget = getattr(event, "widget", None)
        if not isinstance(widget, tk.Text):
            return None

        target_index = widget.index("end-1c")
        widget.mark_set(tk.INSERT, target_index)
        widget.see(target_index)
        return "break"

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
        self._apply_editor_padding(st, self.cfg["editor_padding_px"])
        self._apply_line_number_padding(
            st, self.cfg.get("line_number_padding_px", DEFAULTS["line_number_padding_px"])
        )
        self._schedule_line_number_update(st["frame"], delay_ms=10)

    def _sync_wrap_menu_var(self) -> None:
        if self._wrap_menu_var is None:
            return
        st = self._current_tab_state()
        wrap_word = True if not st else st.get("wrap", "word") != "none"
        self._wrap_menu_var.set(wrap_word)

    def _toggle_follow_stream(self):
        self._set_follow_stream_enabled(
            not self.cfg.get("follow_stream_enabled", True)
        )

    def _on_follow_menu_toggled(self) -> None:
        if self._follow_menu_var is None:
            return
        self._set_follow_stream_enabled(self._follow_menu_var.get())

    def _set_follow_stream_enabled(self, enabled: bool) -> None:
        self.cfg["follow_stream_enabled"] = enabled
        save_config(self.cfg)
        if self._follow_menu_var is not None:
            self._follow_menu_var.set(enabled)
        if not enabled:
            for st in self.tabs.values():
                st["stream_following"] = False
                st["_stream_follow_primed"] = False

    def _toggle_line_numbers(self):
        enabled = not self.cfg.get("line_numbers_enabled", False)
        self.cfg["line_numbers_enabled"] = enabled
        save_config(self.cfg)
        if self._line_numbers_menu_var is not None:
            self._line_numbers_menu_var.set(enabled)
        for st in self.tabs.values():
            self._apply_line_numbers_state(st, enabled)
            self._schedule_line_number_update(st["frame"], delay_ms=10)

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

        self._dictionary = self._dictionary or self._load_dictionary(self._spell_lang)
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

    def _show_error(self, title: str, message: str, detail: str | None = None) -> None:
        try:
            self.clipboard_clear()
            clip_text = message if detail is None else f"{message}\n\nDetails: {detail}"
            self.clipboard_append(clip_text)
        except tk.TclError:
            pass

        messagebox.showerror(title, message, detail=detail)

    # ---------- Library ----------

    def _open_library_resource(self, title: str, resource: Traversable) -> None:
        try:
            with resources.as_file(resource) as path, open(path, encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            self._show_error(
                "Library Error", "Could not load the library file.", detail=f"{title}: {exc}"
            )
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
            self._show_error("Open Error", "Could not open the file.", detail=str(e))

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
            self._show_error("Save Error", "Could not save the file.", detail=str(e))

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
            self._show_error(
                "Save As Error", "Could not save the file as new.", detail=str(e)
            )

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

        match_tag = "find_replace_match"
        self._configure_find_highlight(text, match_tag)
        status_var = tk.StringVar(value="")

        def set_status(message: str) -> None:
            status_var.set(message)

        def update_buttons():
            has_match = bool(text.tag_ranges(match_tag))
            state = "!disabled" if has_match else "disabled"
            replace_btn.state((state,))
            replace_all_btn.state((state,))

        def clear_highlight(reset_status: bool = True):
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            update_buttons()
            if reset_status:
                set_status("")

        def find_next():
            patt = find_var.get()
            if not patt:
                clear_highlight()
                return
            start = text.index(tk.INSERT)
            pos = text.search(patt, start, stopindex=tk.END)
            if not pos:
                pos = text.search(patt, "1.0", stopindex=tk.END)
                if not pos:
                    clear_highlight()
                    set_status("Not found.")
                    return
            end = f"{pos}+{len(patt)}c"
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            text.tag_add("sel", pos, end)
            text.tag_add(match_tag, pos, end)
            text.mark_set(tk.INSERT, end)
            text.see(pos)
            set_status("")
            update_buttons()

        def replace_current():
            patt = find_var.get()
            repl = repl_var.get()
            ranges = text.tag_ranges(match_tag)
            if not patt or not ranges:
                update_buttons()
                return
            start, end = ranges[0], ranges[1]
            text.delete(start, end)
            text.insert(start, repl)
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            text.mark_set(tk.INSERT, f"{start}+{len(repl)}c")
            text.see(start)
            set_status("Replaced current match.")
            update_buttons()
            find_next()

        def replace_all():
            patt = find_var.get()
            repl = repl_var.get()
            if not patt or not text.tag_ranges(match_tag):
                update_buttons()
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
            set_status(f"Replaced {count} occurrences.")
            clear_highlight(reset_status=False)

        def on_find_change(*_):
            clear_highlight()
            set_status("")

        find_var.trace_add("write", on_find_change)

        btn_frame = ttk.Frame(w)
        btn_frame.grid(row=2, column=1, padx=8, pady=6, sticky="ew")
        btn_frame.columnconfigure((0, 1, 2), weight=1)

        ttk.Button(btn_frame, text="Find", command=find_next).grid(
            row=0, column=0, padx=(0, 4), sticky="w"
        )
        replace_btn = ttk.Button(btn_frame, text="Replace", command=replace_current)
        replace_btn.grid(row=0, column=1)
        replace_all_btn = ttk.Button(btn_frame, text="Replace All", command=replace_all)
        replace_all_btn.grid(row=0, column=2, padx=(4, 0), sticky="e")
        update_buttons()

        status = ttk.Label(w, textvariable=status_var, anchor="w")
        status.grid(row=3, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")

        self._prepare_child_window(w)

    def _open_regex_replace_dialog(self):
        st = self._current_tab_state()
        if not st:
            return
        text = st["text"]

        w = tk.Toplevel(self)
        w.title("Regex Find & Replace")
        w.resizable(False, False)
        tk.Label(w, text="Pattern (Python regex):").grid(
            row=0, column=0, padx=8, pady=8, sticky="e"
        )
        tk.Label(w, text="Replacement:").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        ignorecase_var = tk.BooleanVar(value=False)
        multiline_var = tk.BooleanVar(value=False)
        dotall_var = tk.BooleanVar(value=False)
        e1 = tk.Entry(w, width=42, textvariable=find_var)
        e2 = tk.Entry(w, width=42, textvariable=repl_var)
        e1.grid(row=0, column=1, padx=8, pady=8)
        e2.grid(row=1, column=1, padx=8, pady=8)
        e1.focus_set()

        flag_frame = ttk.Frame(w)
        flag_frame.grid(row=2, column=0, columnspan=2, padx=8, sticky="w")
        ttk.Checkbutton(
            flag_frame, text="IGNORECASE", variable=ignorecase_var, onvalue=True, offvalue=False
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Checkbutton(
            flag_frame, text="MULTILINE", variable=multiline_var, onvalue=True, offvalue=False
        ).grid(row=0, column=1, padx=(0, 8))
        ttk.Checkbutton(
            flag_frame, text="DOTALL", variable=dotall_var, onvalue=True, offvalue=False
        ).grid(row=0, column=2, padx=(0, 8))

        match_tag = "regex_replace_match"
        self._configure_find_highlight(text, match_tag)
        status_var = tk.StringVar(value="")

        def set_status(message: str) -> None:
            status_var.set(message)

        def clear_highlight(reset_status: bool = True) -> None:
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            if reset_status:
                set_status("")

        def update_buttons() -> None:
            has_match = bool(text.tag_ranges(match_tag))
            state = "!disabled" if has_match else "disabled"
            replace_btn.state((state,))
            replace_all_btn.state((state,))

        def get_pattern() -> re.Pattern[str] | None:
            patt = find_var.get()
            if not patt:
                clear_highlight()
                return None
            flags = 0
            if ignorecase_var.get():
                flags |= re.IGNORECASE
            if multiline_var.get():
                flags |= re.MULTILINE
            if dotall_var.get():
                flags |= re.DOTALL
            try:
                return re.compile(patt, flags)
            except re.error as exc:
                clear_highlight(reset_status=False)
                set_status(f"Invalid regex: {exc}")
                messagebox.showerror("Regex Error", f"Invalid regex: {exc}")
                update_buttons()
                return None

        def highlight_match(content: str, match: re.Match[str], wrapped: bool) -> None:
            start_idx = offset_to_tkindex(content, match.start())
            end_idx = offset_to_tkindex(content, match.end())
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            text.tag_add("sel", start_idx, end_idx)
            text.tag_add(match_tag, start_idx, end_idx)
            if match.start() == match.end():
                text.mark_set(tk.INSERT, text.index(f"{end_idx}+1c"))
            else:
                text.mark_set(tk.INSERT, end_idx)
            text.see(start_idx)
            if wrapped:
                set_status("Wrapped to the start; continuing search.")
            else:
                set_status("")
            update_buttons()

        def find_next():
            pattern = get_pattern()
            if not pattern:
                return
            content = text.get("1.0", tk.END)
            start_offset = len(text.get("1.0", tk.INSERT))
            match = pattern.search(content, start_offset)
            wrapped = False
            if match is None:
                match = pattern.search(content, 0)
                if match is None:
                    clear_highlight(reset_status=False)
                    set_status("No matches found.")
                    update_buttons()
                    return
                wrapped = start_offset != 0

            highlight_match(content, match, wrapped)

        def replace_current():
            pattern = get_pattern()
            if not pattern:
                return
            ranges = text.tag_ranges(match_tag)
            if not ranges:
                update_buttons()
                return
            start, end = ranges[0], ranges[1]
            match_text = text.get(start, end)
            try:
                replacement = pattern.sub(repl_var.get(), match_text, count=1)
            except re.error as exc:
                messagebox.showerror("Regex Error", f"Replacement failed: {exc}")
                set_status(f"Replacement error: {exc}")
                return
            text.delete(start, end)
            text.insert(start, replacement)
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            new_insert = f"{start}+{len(replacement)}c"
            text.mark_set(tk.INSERT, new_insert)
            text.see(start)
            set_status("Replaced current match.")
            update_buttons()
            find_next()

        def replace_all():
            pattern = get_pattern()
            if not pattern:
                return
            content = text.get("1.0", tk.END)
            try:
                replaced_text, count = pattern.subn(repl_var.get(), content)
            except re.error as exc:
                messagebox.showerror("Regex Error", f"Replacement failed: {exc}")
                set_status(f"Replacement error: {exc}")
                return
            if count == 0:
                clear_highlight(reset_status=False)
                set_status("No matches to replace.")
                update_buttons()
                return
            text.delete("1.0", tk.END)
            text.insert("1.0", replaced_text)
            text.mark_set(tk.INSERT, "1.0")
            text.see("1.0")
            clear_highlight()
            set_status(f"Replaced {count} occurrence(s).")
            update_buttons()

        def on_find_change(*_):
            clear_highlight()
            set_status("")
            update_buttons()

        find_var.trace_add("write", on_find_change)
        ignorecase_var.trace_add("write", on_find_change)
        multiline_var.trace_add("write", on_find_change)
        dotall_var.trace_add("write", on_find_change)

        btn_frame = ttk.Frame(w)
        btn_frame.grid(row=3, column=1, padx=8, pady=6, sticky="ew")
        btn_frame.columnconfigure((0, 1, 2), weight=1)

        ttk.Button(btn_frame, text="Find next", command=find_next).grid(
            row=0, column=0, padx=(0, 4), sticky="w"
        )
        replace_btn = ttk.Button(btn_frame, text="Replace", command=replace_current)
        replace_btn.grid(row=0, column=1)
        replace_all_btn = ttk.Button(btn_frame, text="Replace all", command=replace_all)
        replace_all_btn.grid(row=0, column=2)
        update_buttons()

        status = ttk.Label(w, textvariable=status_var, anchor="w")
        status.grid(row=4, column=0, columnspan=2, padx=8, pady=(0, 8), sticky="ew")

        def on_close() -> None:
            clear_highlight()
            w.destroy()

        w.protocol("WM_DELETE_WINDOW", on_close)
        self._prepare_child_window(w)

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

        def add_combobox_row(r, label, var, values, width=40):
            tk.Label(w, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", padx=8, pady=4
            )
            cb = ttk.Combobox(w, textvariable=var, values=values, width=width)
            cb.grid(row=r, column=1, padx=8, pady=4)
            cb.bind("<<ComboboxSelected>>", lambda e: var.set(cb.get()))
            return cb

        endpoint_var = tk.StringVar(value=cfg["endpoint"])
        temp_var = tk.StringVar(value=str(cfg["temperature"]))
        top_p_var = tk.StringVar(value=str(cfg["top_p"]))

        fim_pref_var = tk.StringVar(value=cfg["fim_prefix"])
        fim_suf_var = tk.StringVar(value=cfg["fim_suffix"])
        fim_mid_var = tk.StringVar(value=cfg["fim_middle"])

        fontfam_var = tk.StringVar(value=cfg["font_family"])
        fontsize_var = tk.StringVar(value=str(cfg["font_size"]))
        pad_var = tk.StringVar(
            value=str(cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"]))
        )
        line_pad_var = tk.StringVar(
            value=str(
                cfg.get(
                    "line_number_padding_px", DEFAULTS["line_number_padding_px"]
                )
            )
        )
        scroll_speed_var = tk.StringVar(
            value=str(
                cfg.get("scroll_speed_multiplier", DEFAULTS["scroll_speed_multiplier"])
            )
        )
        fg_var = tk.StringVar(value=cfg["fg"])
        bg_var = tk.StringVar(value=cfg["bg"])
        highlight1_var = tk.StringVar(value=cfg["highlight1"])
        highlight2_var = tk.StringVar(value=cfg["highlight2"])
        open_maximized_var = tk.BooleanVar(value=cfg.get("open_maximized", False))
        spell_lang_var = tk.StringVar(value=self._spell_lang)
        available_spell_langs = self._available_spell_langs
        show_spell_lang = len(available_spell_langs) > 1

        prev_pad = cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"])
        prev_line_pad = cfg.get(
            "line_number_padding_px", DEFAULTS["line_number_padding_px"]
        )

        row = 0
        add_row(row, "Endpoint (base, no path):", endpoint_var)
        row += 1
        add_row(row, "Temperature:", temp_var)
        row += 1
        add_row(row, "Top-p:", top_p_var)
        row += 1

        tk.Checkbutton(
            w,
            text="Open maximized on startup",
            variable=open_maximized_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=0, columnspan=2, padx=8, pady=4, sticky="w")
        row += 1

        add_combobox_row(
            row,
            "Scroll speed multiplier:",
            scroll_speed_var,
            [str(v) for v in range(1, 11)],
            width=5,
        )
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
        available_fonts = sorted(set(tkfont.families()))
        current_fontfam = fontfam_var.get().strip()
        if current_fontfam and current_fontfam not in available_fonts:
            available_fonts.append(current_fontfam)
        add_combobox_row(row, "Font family:", fontfam_var, available_fonts)
        row += 1
        add_row(row, "Font size:", fontsize_var)
        row += 1
        add_row(row, "Editor padding (px):", pad_var)
        row += 1
        add_row(row, "Line number padding (px):", line_pad_var)
        row += 1

        def pick_color(initial: str, title: str) -> tuple | None:
            c = colorchooser.askcolor(color=initial, title=title, parent=w)
            w.lift()
            return c

        def pick_fg():
            c = pick_color(fg_var.get(), "Pick text color")
            if c and c[1]:
                fg_var.set(c[1])

        def pick_bg():
            c = pick_color(bg_var.get(), "Pick background color")
            if c and c[1]:
                bg_var.set(c[1])

        def pick_highlight1():
            c = pick_color(highlight1_var.get(), "Pick caret/highlight color")
            if c and c[1]:
                highlight1_var.set(c[1])

        def pick_highlight2():
            c = pick_color(highlight2_var.get(), "Pick selection color")
            if c and c[1]:
                highlight2_var.set(c[1])

        tk.Label(w, text="Text color (hex):").grid(row=row, column=0, padx=8, pady=4, sticky="w")
        tk.Entry(w, textvariable=fg_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_fg).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        tk.Label(
            w, text="Background color (hex):"
        ).grid(row=row, column=0, padx=8, pady=4, sticky="w")
        tk.Entry(w, textvariable=bg_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_bg).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        tk.Label(w, text="Caret color (hex):").grid(
            row=row, column=0, padx=8, pady=4, sticky="w"
        )
        tk.Entry(w, textvariable=highlight1_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_highlight1).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        tk.Label(w, text="Selection color (hex):").grid(
            row=row, column=0, padx=8, pady=4, sticky="w"
        )
        tk.Entry(w, textvariable=highlight2_var, width=20).grid(
            row=row, column=1, padx=8, pady=4, sticky="w"
        )
        tk.Button(w, text="Pick…", command=pick_highlight2).grid(
            row=row, column=1, padx=8, pady=4, sticky="e"
        )
        row += 1

        if show_spell_lang:
            add_combobox_row(
                row,
                "Spellcheck language:",
                spell_lang_var,
                available_spell_langs,
            )
            row += 1

        def apply_and_close():
            try:
                self.cfg["endpoint"] = endpoint_var.get().strip().rstrip("/")
                self.cfg["temperature"] = float(temp_var.get())
                self.cfg["top_p"] = float(top_p_var.get())
                self.cfg["fim_prefix"] = fim_pref_var.get()
                self.cfg["fim_suffix"] = fim_suf_var.get()
                self.cfg["fim_middle"] = fim_mid_var.get()
                self.cfg["font_family"] = fontfam_var.get().strip() or DEFAULTS["font_family"]
                self.cfg["font_size"] = max(6, min(72, int(fontsize_var.get())))
                new_pad = max(0, int(pad_var.get()))
                new_line_pad = max(0, int(line_pad_var.get()))
                self.cfg["editor_padding_px"] = new_pad
                self.cfg["line_number_padding_px"] = new_line_pad
                self.cfg["fg"] = fg_var.get().strip()
                self.cfg["bg"] = bg_var.get().strip()
                self.cfg["highlight1"] = highlight1_var.get().strip()
                self.cfg["highlight2"] = highlight2_var.get().strip()
                self.cfg["open_maximized"] = bool(open_maximized_var.get())
                self.cfg["scroll_speed_multiplier"] = max(
                    1, min(10, int(scroll_speed_var.get()))
                )
                if show_spell_lang:
                    self._spell_lang = spell_lang_var.get().strip() or DEFAULTS["spell_lang"]
                    self.cfg["spell_lang"] = self._spell_lang
                else:
                    self._spell_lang = DEFAULTS.get("spell_lang", "en_US")
                    self.cfg.pop("spell_lang", None)
            except Exception as e:
                self._show_error("Settings", "Invalid settings value.", detail=str(e))
                return

            pad_changed = (new_pad != prev_pad) or (new_line_pad != prev_line_pad)
            save_config(self.cfg)
            self._apply_open_maximized(self.cfg["open_maximized"])
            self._dictionary = self._load_dictionary(self._spell_lang)
            self.app_font.config(family=self.cfg["font_family"], size=self.cfg["font_size"])
            for frame, st in self.tabs.items():
                t = st["text"]
                t.configure(
                    font=self.app_font,
                    fg=self.cfg["fg"],
                    bg=self.cfg["bg"],
                    insertbackground=self.cfg["highlight1"],
                    selectbackground=self.cfg["highlight2"],
                    selectforeground=self.cfg["bg"],
                )
                self._configure_find_highlight(t)
                t.tag_configure(
                    "misspelled",
                    underline=True,
                    foreground=self.cfg["highlight1"],
                )
                content_frame = st.get("content_frame")
                if content_frame is not None:
                    content_frame.configure(bg=self.cfg["bg"], highlightthickness=0, bd=0)
                self._apply_editor_padding(st, self.cfg["editor_padding_px"])
                self._apply_line_number_padding(st, self.cfg["line_number_padding_px"])
                if pad_changed:
                    self._reflow_text_layout(st)
                self._clear_line_spacing(t)
                self._render_line_numbers(st)
                self._schedule_line_number_update(frame, delay_ms=15)
                # refresh spellcheck state
                if not self.cfg["spellcheck_enabled"]:
                    t.tag_remove("misspelled", "1.0", "end")
                else:
                    self._schedule_spellcheck_for_frame(frame, delay_ms=200)
            w.destroy()

        tk.Button(w, text="Save", command=apply_and_close).grid(
            row=row, column=1, padx=8, pady=12, sticky="e"
        )

        self._prepare_child_window(w)

    # ---------- Generate (streaming) ----------

    def _should_follow(self, text_widget: tk.Text) -> bool:
        try:
            _first, last = text_widget.yview()
        except Exception:
            return True
        return last >= 0.999

    def _show_unsupported_fim_error(self, exc: TagParseError) -> None:
        self._show_error("Generate", "FIM marker could not be parsed.", detail=str(exc))

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
        st["stream_patterns"] = []
        st["stream_accumulated"] = ""
        st["stream_cancelled"] = False
        st["post_actions"] = []
        stop_event = st.get("stream_stop_event")
        if stop_event is not None:
            stop_event.set()
        st["stream_stop_event"] = None
        st["_stream_prev_autoseparators"] = None

    def _begin_stream_undo_group(self, st):
        text = st["text"]
        try:
            st["_stream_prev_autoseparators"] = text.cget("autoseparators")
            text.configure(autoseparators=False)
            text.edit_separator()
        except tk.TclError:
            st["_stream_prev_autoseparators"] = None

    def _end_stream_undo_group(self, st):
        text = st["text"]
        prev_autoseparators = st.get("_stream_prev_autoseparators")
        with contextlib.suppress(tk.TclError):
            text.edit_separator()

        if prev_autoseparators is not None:
            with contextlib.suppress(tk.TclError):
                text.configure(autoseparators=prev_autoseparators)
        st["_stream_prev_autoseparators"] = None

    def _find_active_tag(self, tokens, cursor_offset: int) -> TagToken | None:
        marker_token: TagToken | None = None
        for token in tokens:
            if not isinstance(token, TagToken):
                continue
            if not cursor_within_span(token.start, token.end, cursor_offset):
                continue
            if marker_token is None or token.start >= marker_token.start:
                marker_token = token
        return marker_token

    def _build_name_registry(self, tokens) -> dict[str, TagToken]:
        registry: dict[str, TagToken] = {}
        for token in tokens:
            if not isinstance(token, TagToken):
                continue
            if token.kind != "fim" or not isinstance(token.tag, FIMTag):
                continue
            for fn in token.tag.functions:
                if fn.name == "name" and fn.args:
                    registry[fn.args[0]] = token
        return registry

    def _run_sequence_step(self, st, *, tokens=None, registry=None):
        if not self._sequence_queue:
            self._sequence_tab = None
            self._sequence_names = None
            return

        if self._fim_generation_active:
            return

        tab_id = self.nb.select()
        if self._sequence_tab is not None and tab_id != self._sequence_tab:
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            return

        name = self._sequence_queue.pop(0)
        text_widget = st["text"]
        content = text_widget.get("1.0", tk.END)

        completed = set(self._sequence_names or ()) - set(self._sequence_queue)
        completed.discard(name)

        try:
            tokens = tokens or list(
                parse_triple_tokens(
                    content, allow_missing_sequence_names=completed
                )
            )
        except TagParseError as exc:
            self._show_unsupported_fim_error(exc)
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            return

        registry = registry or self._build_name_registry(tokens)
        marker_token = registry.get(name)
        if marker_token is None or not isinstance(marker_token.tag, FIMTag):
            self._show_error(
                "Generate", "Sequence tag is missing a reference.", detail=name
            )
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            return

        try:
            fim_request = parse_fim_request(
                content, marker_token.start, tokens=tokens, marker_token=marker_token
            )
        except TagParseError as exc:
            self._show_unsupported_fim_error(exc)
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            return
        if fim_request is None:
            self._show_error(
                "Generate", "FIM tag reference is invalid.", detail=name
            )
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            return

        self._launch_fim_or_completion_stream(st, content, fim_request)

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
        cfg = self.__dict__.get("cfg") or {}
        follow_enabled = cfg.get("follow_stream_enabled", True)
        if follow_enabled:
            should_follow = st.get("stream_following", self._should_follow(text))
        else:
            should_follow = False
            st["stream_following"] = False
            st["_stream_follow_primed"] = False
        text.insert(cur, piece)
        st["stream_accumulated"] = st.get("stream_accumulated", "") + piece
        with contextlib.suppress(tk.TclError):
            text.tag_remove("misspelled", cur, f"{cur}+{len(piece)}c")
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
        elif follow_enabled and self._should_follow(text):
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
        if self._fim_generation_active:
            self._show_error(
                "Generate",
                "A FIM generation is already running.",
                detail="Please wait for the current request to finish.",
            )
            return

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

        try:
            tokens = list(parse_triple_tokens(content))
        except TagParseError as exc:
            self._show_unsupported_fim_error(exc)
            return

        marker_token = self._find_active_tag(tokens, cursor_offset)
        if marker_token is None:
            messagebox.showinfo(
                "Generate",
                "Place the caret inside a [[[N]]] marker to generate.",
            )
            return

        name_registry = self._build_name_registry(tokens)
        if marker_token.kind == "sequence" and isinstance(marker_token.tag, SequenceTag):
            names = list(marker_token.tag.names)
            missing = [nm for nm in names if nm not in name_registry]
            if missing:
                self._show_error(
                    "Generate",
                    "Sequence references are missing tags.",
                    detail=", ".join(missing),
                )
                return
            self._sequence_queue = names
            self._sequence_tab = self.nb.select()
            self._sequence_names = tuple(names)
            self._run_sequence_step(st, tokens=tokens, registry=name_registry)
            return

        try:
            fim_request = parse_fim_request(
                content, cursor_offset, tokens=tokens, marker_token=marker_token
            )
        except TagParseError as exc:
            self._show_unsupported_fim_error(exc)
            return
        if fim_request is not None:
            self._sequence_queue = []
            self._sequence_tab = None
            self._sequence_names = None
            self._launch_fim_or_completion_stream(st, content, fim_request)
            return

        messagebox.showinfo(
            "Generate",
            "Place the caret inside a [[[N]]] marker to generate.",
        )

    def _on_generate_shortcut(self, event):
        self.generate()
        return "break"

    def _on_interrupt_stream(self, event):
        self.interrupt_stream()
        return "break"

    def _on_show_fim_log_shortcut(self, event):
        self._open_fim_log_tab()
        return "break"

    def interrupt_stream(self):
        if not self._fim_generation_active:
            return

        st = self._current_tab_state()
        if not st:
            return

        st["stream_cancelled"] = True
        st["stream_patterns"] = []
        st["stream_accumulated"] = ""
        self._sequence_queue = []
        self._sequence_tab = None
        self._sequence_names = None

        stop_event = st.get("stream_stop_event")
        if stop_event is not None:
            stop_event.set()

        self._result_queue.put(
            {"ok": True, "kind": "stream_done", "tab": self.nb.select()}
        )

    def paste_last_fim_tag(self):
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

        with contextlib.suppress(tk.TclError):
            text_widget.mark_set(tk.INSERT, f"{start_index}+{len(marker)}c")

        text_widget.tag_remove("sel", "1.0", tk.END)
        text_widget.see(tk.INSERT)
        text_widget.focus_set()

    def repeat_last_fim(self):
        if self._fim_generation_active:
            self._show_error(
                "Generate",
                "A FIM generation is already running.",
                detail="Please wait for the current request to finish.",
            )
            return

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

        body_offset = marker.find("[[[")
        if body_offset == -1:
            body_offset = 0
        else:
            body_offset += 3
        while body_offset < len(marker) and marker[body_offset].isspace():
            body_offset += 1

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

    def _on_paste_last_fim_tag_shortcut(self, event):
        self.paste_last_fim_tag()
        return "break"

    # ----- FIM/completion streaming -----

    def _launch_fim_or_completion_stream(self, st, content, fim_request: FIMRequest):
        cfg = self.cfg
        self._last_fim_marker = fim_request.marker.raw
        self._log_fim_generation(fim_request)

        request_cfg = {
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "max_tokens": fim_request.max_tokens,
        }
        request_cfg.update(fim_request.config_overrides)

        if fim_request.use_completion:
            prompt = fim_request.before_region
        else:
            prompt = (
                f"{cfg['fim_prefix']}{fim_request.before_region}{cfg['fim_suffix']}{fim_request.safe_suffix}{cfg['fim_middle']}"
            )

        payload = {
            "prompt": prompt,
            "max_tokens": request_cfg.get("max_tokens", fim_request.max_tokens),
            "temperature": request_cfg.get("temperature", cfg["temperature"]),
            "top_p": request_cfg.get("top_p", cfg["top_p"]),
            "stream": True,
        }
        text = st["text"]
        start_index = offset_to_tkindex(content, fim_request.marker.start)
        end_index = offset_to_tkindex(content, fim_request.marker.end)

        self._reset_stream_state(st)
        self._begin_stream_undo_group(st)

        self._fim_generation_active = True
        try:
            st["stream_patterns"] = [
                {"text": patt, "action": "stop"} for patt in fim_request.stop_patterns
            ] + [
                {"text": patt, "action": "chop"} for patt in fim_request.chop_patterns
            ]
            st["stream_accumulated"] = ""
            st["stream_cancelled"] = False
            st["stream_stop_event"] = threading.Event()
            st["post_actions"] = []

            for fn in fim_request.post_functions:
                val = fn.args[0] if fn.args else ""
                if fn.name == "append_nl" and not val.endswith("\n"):
                    val = f"{val}\n"
                st["post_actions"].append(val)

            self._set_busy(True)

            # Prepare streaming mark
            text.mark_set("stream_here", start_index)
            text.mark_gravity("stream_here", tk.RIGHT)
            if (
                fim_request.suffix_token is not None
                and not fim_request.keep_tags
                and isinstance(fim_request.suffix_token.tag, PrefixSuffixTag)
                and fim_request.suffix_token.tag.hardness == "soft"
            ):
                s_s = offset_to_tkindex(content, fim_request.suffix_token.start)
                s_e = offset_to_tkindex(content, fim_request.suffix_token.end)
                with contextlib.suppress(tk.TclError):
                    text.delete(s_s, s_e)
            if (
                fim_request.prefix_token is not None
                and not fim_request.keep_tags
                and isinstance(fim_request.prefix_token.tag, PrefixSuffixTag)
                and fim_request.prefix_token.tag.hardness == "soft"
            ):
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

            def worker(tab_id, stop_event):
                try:
                    for piece in stream_completion(cfg["endpoint"], payload, stop_event):
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
                    self._result_queue.put(
                        {"ok": False, "error": str(e), "tab": tab_id}
                    )
                finally:
                    # Always emit done; then kick spellcheck
                    self._result_queue.put(
                        {"ok": True, "kind": "stream_done", "tab": tab_id}
                    )
                    self._result_queue.put(
                        {"ok": True, "kind": "spellcheck_now", "tab": tab_id}
                    )

            threading.Thread(
                target=worker,
                args=(self.nb.select(), st["stream_stop_event"]),
                daemon=True,
            ).start()
        except Exception as exc:
            self._fim_generation_active = False
            self._set_busy(False)
            with contextlib.suppress(Exception):
                self._end_stream_undo_group(st)
            self._show_error("Generation Error", "Generation failed to start.", detail=str(exc))
            return

    # ---------- Queue handling ----------

    def _poll_queue(self):
        try:
            while True:
                item = self._result_queue.get_nowait()

                try:
                    st = None
                    if not item.get("ok"):
                        tab_id = item.get("tab")
                        frame = self.nametowidget(tab_id) if tab_id else None
                        st_err = None
                        if frame in self.tabs:
                            st_err = self.tabs[frame]
                            mark = st_err.get("stream_mark") or "stream_here"
                            self._force_flush_stream_buffer(frame, mark)
                            self._end_stream_undo_group(st_err)
                        self._fim_generation_active = False
                        self._set_busy(False)
                        self._sequence_queue = []
                        self._sequence_tab = None
                        self._sequence_names = None
                        self._show_error(
                            "Generation Error",
                            "Generation failed during streaming.",
                            detail=item.get("error", "Unknown error"),
                        )
                        continue

                    kind = item.get("kind")
                    tab_id = item.get("tab")
                    frame = self.nametowidget(tab_id) if tab_id else None
                    if not frame or frame not in self.tabs:
                        if kind == "stream_done":
                            self._fim_generation_active = False
                            self._set_busy(False)
                        continue
                    st = self.tabs[frame]
                    text = st["text"]

                    if kind == "stream_append":
                        if st.get("stream_cancelled") and not item.get("allow_stream_cancelled"):
                            continue

                        mark = item["mark"]
                        piece = item["text"]

                        if not item.get("allow_stream_cancelled"):
                            patterns = st.get("stream_patterns", [])
                            buffered = "".join(st.get("stream_buffer", []))
                            accumulated = st.get("stream_accumulated", "")
                            if patterns:
                                candidate = f"{accumulated}{buffered}{piece}"
                                match = find_stream_match(candidate, patterns)

                                if match is not None:
                                    target_text = (
                                        candidate[: match.match_index]
                                        if match.action == "chop"
                                        else candidate[: match.end_index]
                                    )
                                    pending_insert = target_text[len(accumulated) :]
                                    if pending_insert:
                                        st["stream_buffer"] = [pending_insert]
                                    else:
                                        st["stream_buffer"].clear()
                                    st["stream_mark"] = mark
                                    flush_mark = st.get("stream_mark") or "stream_here"
                                    self._force_flush_stream_buffer(frame, flush_mark)
                                    st["stream_cancelled"] = True
                                    st["stream_patterns"] = []
                                    st["stream_accumulated"] = target_text
                                    stop_event = st.get("stream_stop_event")
                                    if stop_event is not None:
                                        stop_event.set()
                                    self._result_queue.put(
                                        {"ok": True, "kind": "stream_done", "tab": tab_id}
                                    )
                                    self._result_queue.put(
                                        {"ok": True, "kind": "spellcheck_now", "tab": tab_id}
                                    )
                                    continue

                            st["stream_buffer"] = [buffered + piece]
                            st["stream_accumulated"] = accumulated
                        else:
                            st["stream_buffer"].append(piece)
                            st["stream_accumulated"] = st.get("stream_accumulated", "") + piece

                        st["stream_mark"] = mark
                        self._schedule_stream_flush(frame, mark)

                    elif kind == "stream_done":
                        mark = st.get("stream_mark") or item.get("mark") or "stream_here"
                        self._force_flush_stream_buffer(frame, mark)
                        st["stream_patterns"] = []
                        st["stream_accumulated"] = ""
                        st["stream_stop_event"] = None
                        for extra in st.get("post_actions", []):
                            try:
                                text.insert(mark, extra)
                                mark = text.index(f"{mark}+{len(extra)}c")
                            except tk.TclError:
                                continue
                        st["post_actions"] = []
                        self._end_stream_undo_group(st)
                        self._fim_generation_active = False
                        self._set_busy(False)
                        self._set_dirty(st, True)
                        if self._sequence_queue and self._sequence_tab == tab_id:
                            self.after_idle(lambda st=st: self._run_sequence_step(st))

                    elif kind == "spellcheck_now":
                        self._schedule_spellcheck_for_frame(frame, delay_ms=150)

                    elif kind == "spell_result":
                        # Apply tag updates
                        region = item.get("region")
                        if region:
                            start_region, end_region = region
                            text.tag_remove("misspelled", start_region, end_region)
                        else:
                            text.tag_remove("misspelled", "1.0", "end")
                        for sidx, eidx in item.get("spans", []):
                            text.tag_add("misspelled", sidx, eidx)

                except Exception as exc:  # noqa: BLE001
                    self._fim_generation_active = False
                    self._set_busy(False)
                    self._sequence_queue = []
                    self._sequence_tab = None
                    self._sequence_names = None
                    with contextlib.suppress(Exception):
                        self._end_stream_undo_group(st)
                    self._show_error(
                        "Generation Error",
                        "Streaming update failed.",
                        detail=str(exc),
                    )

        except queue.Empty:
            pass
        finally:
            self.after(60, self._poll_queue)

    # ---------- Spellcheck (enchant) ----------

    def _list_spell_languages(self) -> list[str]:
        try:
            langs = enchant.list_languages()
        except Exception:
            return []

        available: list[str] = []
        for lang in sorted(set(langs or [])):
            if not lang:
                continue
            try:
                if enchant.dict_exists(lang):
                    available.append(lang)
            except Exception:
                continue

        default_lang = DEFAULTS.get("spell_lang", "en_US")
        if default_lang not in available:
            try:
                if enchant.dict_exists(default_lang):
                    available.append(default_lang)
            except Exception:
                pass

        return sorted(available)

    def _determine_spell_language(self, preferred: str | None) -> str:
        default_lang = DEFAULTS.get("spell_lang", "en_US")
        if len(self._available_spell_langs) <= 1:
            if "spell_lang" in self.cfg:
                self.cfg.pop("spell_lang", None)
                save_config(self.cfg)
            return default_lang

        lang = preferred or default_lang
        if lang not in self._available_spell_langs:
            if default_lang in self._available_spell_langs:
                lang = default_lang
            else:
                lang = self._available_spell_langs[0]

        if self.cfg.get("spell_lang") != lang:
            self.cfg["spell_lang"] = lang
            save_config(self.cfg)
        return lang

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

    @staticmethod
    def _relative_index_to_absolute(
        base_line: int, base_col: int, relative_index: str
    ) -> str:
        rel_line_str, rel_col_str = relative_index.split(".")
        rel_line = int(rel_line_str)
        rel_col = int(rel_col_str)
        abs_line = base_line + rel_line - 1
        abs_col = rel_col + (base_col if rel_line == 1 else 0)
        return f"{abs_line}.{abs_col}"

    def _spell_region_for_text(self, text: tk.Text) -> tuple[str, str, int, int]:
        try:
            total_lines = int(text.index("end-1c").split(".")[0])
        except Exception:
            return "1.0", "end-1c", 1, 0
        threshold = int(
            self.cfg.get(
                "spellcheck_full_document_line_threshold",
                DEFAULTS["spellcheck_full_document_line_threshold"],
            )
        )
        if total_lines <= threshold:
            start_idx = "1.0"
            end_idx = "end-1c"
        else:
            buffer_lines = int(
                self.cfg.get(
                    "spellcheck_view_buffer_lines",
                    DEFAULTS["spellcheck_view_buffer_lines"],
                )
            )
            try:
                first_visible = text.index("@0,0")
                last_visible = text.index(f"@0,{text.winfo_height()}")
            except tk.TclError:
                first_visible = "1.0"
                last_visible = "1.0"

            start_line = max(1, int(first_visible.split(".")[0]) - buffer_lines)
            end_line = min(total_lines, int(last_visible.split(".")[0]) + buffer_lines)

            start_idx = f"{start_line}.0"
            try:
                end_idx = text.index(f"{end_line}.end")
            except tk.TclError:
                end_idx = text.index("end-1c")

        base_line_str, base_col_str = start_idx.split(".")
        return start_idx, end_idx, int(base_line_str), int(base_col_str)

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
        st["_spell_timer"] = None
        t = st["text"]
        # Snapshot text (must be on main thread)
        try:
            region_start, region_end, base_line, base_col = self._spell_region_for_text(t)
        except AttributeError:
            region_start, region_end, base_line, base_col = FIMPad._spell_region_for_text(
                self, t
            )
        txt = t.get(region_start, region_end)
        ignore = set(self._spell_ignore)  # copy
        dictionary = getattr(self, "_dictionary", None)
        region = (region_start, region_end)

        def worker(
            tab_id, text_snapshot, ignore_set, dict_obj, base_ln: int, base_col: int, span_region
        ):
            def emit(spans: list[tuple[str, str]]):
                self._result_queue.put(
                    {
                        "ok": True,
                        "kind": "spell_result",
                        "tab": tab_id,
                        "spans": spans,
                        "region": span_region,
                    }
                )

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
                    emit([])
                    return

                if dict_obj:
                    miss = set()
                    for w in set(words):
                        if not dict_obj.check(w):
                            miss.add(w)

                    miss = {w for w in miss if w not in ignore_set}

                    if not miss:
                        emit([])
                        return

                    content = text_snapshot
                    out_spans = []
                    for w, (s_off, e_off) in zip(words, offsets, strict=False):
                        if w in miss:
                            sidx_rel = offset_to_tkindex(content, s_off)
                            eidx_rel = offset_to_tkindex(content, e_off)
                            sidx = FIMPad._relative_index_to_absolute(base_ln, base_col, sidx_rel)
                            eidx = FIMPad._relative_index_to_absolute(base_ln, base_col, eidx_rel)
                            out_spans.append((sidx, eidx))
                    emit(out_spans)
                    return

                # Fallback path for environments without dictionaries (used by tests)
                if not dict_obj:
                    lang = self._spell_lang
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
                        emit([])
                        return

                    content = text_snapshot
                    out_spans = []
                    for w, (s_off, e_off) in zip(words, offsets, strict=False):
                        if w in miss:
                            sidx_rel = offset_to_tkindex(content, s_off)
                            eidx_rel = offset_to_tkindex(content, e_off)
                            sidx = FIMPad._relative_index_to_absolute(base_ln, base_col, sidx_rel)
                            eidx = FIMPad._relative_index_to_absolute(base_ln, base_col, eidx_rel)
                            out_spans.append((sidx, eidx))
                    emit(out_spans)
                    return
            except Exception:
                # swallow spell errors silently
                emit([])

        threading.Thread(
            target=worker,
            args=(
                self.nb.select(),
                txt,
                ignore,
                dictionary,
                base_line,
                base_col,
                region,
            ),
            daemon=True,
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
