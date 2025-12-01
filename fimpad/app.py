#!/usr/bin/env python3
"""
FIMpad — Tabbed Tkinter editor for llama-server
with FIM streaming, dirty tracking, and enchant-based spellcheck.
"""

import contextlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from importlib import resources
from importlib.resources.abc import Traversable
from tkinter import colorchooser, messagebox, simpledialog, ttk

import enchant

from .bol_utils import (
    _deindent_block,
    _delete_leading_chars,
    _indent_block,
    _prepend_to_lines,
    _spaces_to_tabs,
    _tabs_to_spaces,
)
from .client import stream_completion
from .config import CONFIG_PATH, DEFAULTS, WORD_RE, ConfigSaveError, load_config, save_config
from .icons import set_app_icon
from .library_resources import iter_library
from .parser import (
    TRIPLE_RE,
    ConfigTag,
    FIMRequest,
    FIMTag,
    PrefixSuffixTag,
    TagParseError,
    TagToken,
    _parse_tag,
    cursor_within_span,
    parse_fim_request,
    parse_triple_tokens,
)
from .stream_utils import find_stream_match
from .utils import offset_to_tkindex

CORE_TK_FONT_NAMES: tuple[str, ...] = (
    "TkDefaultFont",
    "TkTextFont",
    "TkFixedFont",
    "TkMenuFont",
    "TkHeadingFont",
    "TkIconFont",
    "TkTooltipFont",
    "TkSmallCaptionFont",
    "TkCaptionFont",
)


class FIMPad(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FIMpad 0.0.11")
        set_app_icon(self)
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
        self._settings_window: tk.Toplevel | None = None
        self._text_shortcut_bindings: list[tuple[str, Callable[[tk.Event], str | None]]] = []
        self._register_shortcuts()
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

        self._fim_log: list[str] = []
        self._log_tab_frame: tk.Widget | None = None

        self._last_fim_marker: str | None = None
        self._last_tab: str | None = None
        self._fim_generation_active: bool = False

        self._new_tab()
        self.after_idle(lambda: self._schedule_spellcheck_for_frame(self.nb.select(), delay_ms=50))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _persist_config(self) -> None:
        try:
            save_config(self.cfg)
        except ConfigSaveError as exc:
            self._show_error(
                "Config Save Failed",
                f"Could not save settings to {CONFIG_PATH}.",
                detail=str(exc),
            )

    def _center_window(self, window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
        parent_widget = parent or window.master or self
        try:
            parent_widget = parent_widget.winfo_toplevel()
            window.update_idletasks()
            parent_x = parent_widget.winfo_rootx()
            parent_y = parent_widget.winfo_rooty()
            parent_w = parent_widget.winfo_width()
            parent_h = parent_widget.winfo_height()
            win_w = max(window.winfo_width(), window.winfo_reqwidth())
            win_h = max(window.winfo_height(), window.winfo_reqheight())
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

    def _make_shortcut_handler(
        self, callback: Callable[[], None]
    ) -> Callable[[tk.Event], str]:
        def handler(_event: tk.Event | None = None) -> str:
            callback()
            return "break"

        return handler

    @staticmethod
    def _normalize_sequence(seq: str) -> str:
        return (
            seq.replace("KeyPress-", "")
            .replace("KeyRelease-", "")
            .replace("Key-", "")
            .lower()
        )

    @staticmethod
    def _uppercase_keysym_sequence(seq: str) -> str | None:
        match = re.fullmatch(r"<(.+)-([a-z])>", seq)
        if not match:
            return None
        prefix, key = match.groups()
        return f"<{prefix}-{key.upper()}>"

    def _shortcut_variants(self, sequence: str) -> list[str]:
        variants = [sequence]
        uppercase = self._uppercase_keysym_sequence(sequence)
        if uppercase and uppercase not in variants:
            variants.append(uppercase)
        return variants

    def _register_shortcuts(self) -> None:
        self._text_shortcut_bindings.clear()

        def add(sequence: str, callback: Callable[[], None]) -> None:
            handler = self._make_shortcut_handler(callback)
            for seq in self._shortcut_variants(sequence):
                self.bind_all(seq, handler, add="+")
                self._text_shortcut_bindings.append((seq, handler))

        add("<Control-n>", self._new_tab)
        add("<Control-o>", self._open_file_into_current)
        add("<Control-s>", self._save_file_current)
        add("<Control-Shift-s>", self._save_file_as_current)
        add("<Control-w>", self._close_current_tab)
        add("<Control-q>", self._on_close)
        add("<Control-z>", lambda: self._event_on_current_text("<<Undo>>"))
        add("<Control-Shift-z>", lambda: self._event_on_current_text("<<Redo>>"))
        add("<Control-x>", lambda: self._event_on_current_text("<<Cut>>"))
        add("<Control-c>", lambda: self._event_on_current_text("<<Copy>>"))
        add("<Control-v>", lambda: self._event_on_current_text("<<Paste>>"))
        add("<Delete>", lambda: self._event_on_current_text("<<Clear>>"))
        add("<Control-a>", self._select_all_current)
        add("<Control-f>", self._open_replace_dialog)
        add("<Control-r>", self._open_regex_replace_dialog)
        add("<Control-b>", self._open_bol_tool)
        add("<Control-g>", self._open_settings)
        add("<Alt-w>", self._toggle_wrap_current)
        add("<Alt-f>", self._toggle_follow_stream)
        add("<Alt-n>", self._toggle_line_numbers)
        add("<Alt-s>", self._toggle_spellcheck)
        add("<Alt-g>", self.generate)
        add("<Alt-r>", self.repeat_last_fim)
        add("<Alt-p>", self.paste_last_fim_tag)
        add("<Alt-c>", self.apply_config_tag)
        add("<Alt-j>", self.paste_current_config)
        add("<Alt-i>", self.interrupt_stream)
        add("<Alt-v>", self.validate_tags_current)
        add("<Alt-l>", self.show_fim_log)

        for idx in range(1, 10):
            add(f"<Alt-Key-{idx}>", lambda idx=idx - 1: self._select_tab_by_index(idx))
        add("<Alt-Key-0>", lambda: self._select_tab_by_index(9))
        add("<Control-Prior>", lambda: self._select_tab_by_offset(-1))
        add("<Control-Next>", lambda: self._select_tab_by_offset(1))

    def _disable_builtin_text_shortcuts(self, text: tk.Text) -> None:
        allowed = {
            "<home>",
            "<end>",
            "<control-home>",
            "<control-end>",
            "<shift-home>",
            "<shift-end>",
            "<control-shift-home>",
            "<control-shift-end>",
        }
        custom_shortcuts = {
            self._normalize_sequence(seq) for seq, _handler in self._text_shortcut_bindings
        }
        def swallow(_event: tk.Event | None = None) -> str:
            return "break"
        try:
            class_sequences = text.bind_class("Text") or []
        except tk.TclError:
            return

        for sequence in class_sequences:
            normalized = self._normalize_sequence(sequence)
            if normalized in allowed:
                continue
            if not any(
                modifier in normalized
                for modifier in ("<control-", "<alt-", "<meta-", "<command-", "<option-")
            ):
                continue
            if normalized in custom_shortcuts:
                continue
            text.bind(sequence, swallow)

    def _bind_shortcuts_to_text(self, text: tk.Text) -> None:
        for sequence, handler in self._text_shortcut_bindings:
            text.bind(sequence, handler)

    def _lift_if_exists(self, widget: tk.Misc, above: tk.Misc | None = None) -> None:
        with contextlib.suppress(tk.TclError):
            if widget.winfo_exists():
                if above is not None:
                    widget.lift(above)
                else:
                    widget.lift()

    def _prepare_child_window(self, window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
        parent_widget = parent or window.master or self
        with contextlib.suppress(tk.TclError):
            window.withdraw()

        def keep_above_parent(_event: tk.Event | None = None) -> None:
            self._lift_if_exists(window, parent_widget)

        with contextlib.suppress(tk.TclError):
            parent_widget = parent_widget.winfo_toplevel()
            window.transient(parent_widget)
            window.attributes("-topmost", True)
            window.after(60, lambda: window.attributes("-topmost", False))
            self._lift_if_exists(parent_widget)
            parent_widget.bind("<FocusIn>", keep_above_parent, add="+")
            parent_widget.bind("<Configure>", keep_above_parent, add="+")
            parent_widget.bind("<ButtonPress>", keep_above_parent, add="+")

        window.bind(
            "<FocusIn>", lambda e, p=parent_widget: self._lift_if_exists(e.widget, p), add="+"
        )
        self._center_window(window, parent_widget)
        with contextlib.suppress(tk.TclError):
            window.deiconify()
            window.lift(parent_widget)

    def _configure_find_highlight(self, text: tk.Text, tag: str = "find_replace_match") -> None:
        selection_fg = (
            self.cfg["bg"] if self.cfg.get("reverse_selection_fg", False) else self.cfg["fg"]
        )
        text.tag_configure(
            tag,
            background=self.cfg["highlight2"],
            foreground=selection_fg,
        )

    def _available_font_families(self) -> list[str]:
        available_fonts_set = set(tkfont.families())
        for font_name in CORE_TK_FONT_NAMES:
            with contextlib.suppress(tk.TclError):
                tkfont.nametofont(font_name)
                available_fonts_set.add(font_name)

        current_fontfam = (self.cfg.get("font_family") or DEFAULTS["font_family"]).strip()
        if current_fontfam:
            available_fonts_set.add(current_fontfam)

        return sorted(available_fonts_set)

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

    def _new_tab(self, content: str = "", title: str = "Untitled", *, is_log: bool = False):
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
        selection_fg = (
            self.cfg["bg"] if self.cfg.get("reverse_selection_fg", False) else self.cfg["fg"]
        )
        text.configure(
            font=self.app_font,
            fg=self.cfg["fg"],
            bg=self.cfg["bg"],
            insertbackground=self.cfg["highlight1"],
            selectbackground=self.cfg["highlight2"],
            selectforeground=selection_fg,
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
            "stream_active": False,
            "stream_following": False,
            "_stream_follow_primed": False,
            "_stream_follow_job": None,
            "_pending_follow_mark": None,
            "stream_patterns": [],
            "stream_accumulated": "",
            "stream_cancelled": False,
            "stream_stop_event": None,
            "post_actions": [],
            "last_insert": "1.0",
            "last_yview": 0.0,
            "line_numbers_enabled": self.cfg.get("line_numbers_enabled", False),
            "_line_number_job": None,
            "is_log_tab": is_log,
            "text_tool_window": None,
            "text_tool_type": None,
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
        self._disable_builtin_text_shortcuts(text)
        self._bind_shortcuts_to_text(text)
        text.bind("<<Paste>>", self._on_text_paste, add="+")
        text.bind("<Home>", self._on_home_key)
        text.bind("<End>", self._on_end_key)
        text.bind("<Control-Home>", self._on_ctrl_home_key)
        text.bind("<Control-End>", self._on_ctrl_end_key)

        def on_modified(event=None):
            if st["suppress_modified"] or st.get("is_log_tab"):
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

        if is_log:
            text.config(state=tk.DISABLED)
            text.edit_modified(False)

        self.tabs[frame] = st
        self.nb.add(frame, text=title)
        self._apply_tab_title(frame, title)
        self.nb.select(frame)

        if self._last_tab is None:
            self._last_tab = self.nb.select()

        text.focus_set()
        if is_log:
            with contextlib.suppress(tk.TclError):
                text.mark_set("insert", tk.END)
                text.see(tk.END)
        else:
            text.mark_set("insert", "1.0")
            text.see("1.0")

        self._apply_line_numbers_state(st, st["line_numbers_enabled"])

        # Initial spellcheck (debounced)
        self._schedule_spellcheck_for_frame(frame, delay_ms=250)
        self._sync_wrap_menu_var()
        self._sync_line_numbers_menu_var()
        self._schedule_line_number_update(frame, delay_ms=10)

        return st

    def _on_tab_changed(self, event=None):
        previous = self._last_tab
        if previous:
            self._store_tab_view(previous)
            self._withdraw_tab_text_tool(previous)

        current = self.nb.select()
        if current:
            try:
                frame = self.nametowidget(current)
            except Exception:
                frame = None
            st = self.tabs.get(frame) if frame else None
            if st and self._is_log_tab(st):
                self._scroll_log_tab_to_end(st)
            else:
                self._restore_tab_view(current)
            self._restore_tab_text_tool(current)
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

    def _withdraw_tab_text_tool(self, tab_id: str) -> None:
        try:
            frame = self.nametowidget(tab_id)
        except Exception:
            return
        st = self.tabs.get(frame)
        if not st:
            return

        window = st.get("text_tool_window")
        if not window:
            return
        try:
            if window.winfo_exists():
                with contextlib.suppress(tk.TclError):
                    window.withdraw()
            else:
                self._clear_text_tool_window(st)
        except tk.TclError:
            self._clear_text_tool_window(st)

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
        text.focus_set()
        self._schedule_line_number_update(frame, delay_ms=10)

    def _restore_tab_text_tool(self, tab_id: str) -> None:
        try:
            frame = self.nametowidget(tab_id)
        except Exception:
            return
        st = self.tabs.get(frame)
        if not st:
            return

        window = st.get("text_tool_window")
        if not window:
            return
        try:
            if window.winfo_exists():
                with contextlib.suppress(tk.TclError):
                    window.deiconify()
                    window.lift()
            else:
                self._clear_text_tool_window(st)
        except tk.TclError:
            self._clear_text_tool_window(st)

    def _log_fim_generation(self, fim_request: FIMRequest, response: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        if fim_request.use_completion:
            prefix_text = fim_request.before_region
            mode = "completion generation"
        else:
            prefix_text = f"{self.cfg['fim_prefix']}{fim_request.before_region}"
            suffix_text = (
                f"{self.cfg['fim_suffix']}{fim_request.safe_suffix}{self.cfg['fim_middle']}"
            )
            mode = "FIM generation"

        entry = {
            "time": timestamp,
            "tag": fim_request.marker.raw,
            "mode": mode,
            "prefix": prefix_text,
            "response": response,
        }
        if not fim_request.use_completion:
            entry["suffix"] = suffix_text
        json_block = json.dumps(entry, ensure_ascii=False, indent=4)
        previous_len = len(self._fim_log)
        self._fim_log.append(json_block)

        changed = self._apply_log_retention()
        if changed or len(self._fim_log) != previous_len:
            self._refresh_log_tab_contents()

    def _apply_log_retention(self) -> bool:
        limit = int(self.cfg.get("log_entries_kept", DEFAULTS["log_entries_kept"]))
        limit = max(0, min(9999, limit))
        if limit == 0:
            if self._fim_log:
                self._fim_log.clear()
                return True
            return False

        if len(self._fim_log) > limit:
            del self._fim_log[: len(self._fim_log) - limit]
            return True
        return False

    def _render_fim_log_body(self) -> str:
        if not self._fim_log:
            return "FIM Generation Log is empty.\n"
        return "\n\n".join(self._fim_log) + "\n"

    def _refresh_log_tab_contents(self) -> None:
        frame = self._log_tab_frame
        if frame is None:
            return

        st = self.tabs.get(frame)
        if not st:
            self._log_tab_frame = None
            return

        text: tk.Text | None = st.get("text")
        if not text or not text.winfo_exists():
            self._log_tab_frame = None
            return

        log_body = self._render_fim_log_body()
        st["suppress_modified"] = True
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        text.insert("1.0", log_body)
        text.edit_modified(False)
        st["suppress_modified"] = False
        text.config(state=tk.DISABLED)
        self._scroll_log_tab_to_end(st)

    def _open_fim_log_tab(self) -> None:
        if self._log_tab_frame is not None:
            tab_id = str(self._log_tab_frame)
            if self._log_tab_frame.winfo_exists() and tab_id in self.nb.tabs():
                with contextlib.suppress(tk.TclError):
                    self.nb.select(tab_id)
                    return
            self._log_tab_frame = None

        log_body = self._render_fim_log_body()
        st = self._new_tab(content=log_body, title="FIMpad_log.json", is_log=True)
        self._log_tab_frame = st["frame"]
        self._scroll_log_tab_to_end(st)

    def show_fim_log(self) -> None:
        self._open_fim_log_tab()

    def _current_tab_state(self):
        tab = self.nb.select()
        if not tab:
            return None
        frame = self.nametowidget(tab)
        return self.tabs.get(frame)

    def _is_log_tab(self, st: dict | None) -> bool:
        return bool(st and st.get("is_log_tab"))

    def _clear_text_tool_window(self, st: dict, window: tk.Misc | None = None) -> None:
        if window is not None and st.get("text_tool_window") is not window:
            return
        st["text_tool_window"] = None
        st["text_tool_type"] = None

    def _destroy_text_tool_window(self, st: dict) -> None:
        window = st.get("text_tool_window")
        if window is not None:
            with contextlib.suppress(tk.TclError):
                if window.winfo_exists():
                    window.destroy()
        self._clear_text_tool_window(st)

    def _track_text_tool_window(self, st: dict, window: tk.Misc, tool_type: str) -> None:
        st["text_tool_window"] = window
        st["text_tool_type"] = tool_type

        def on_destroy(event: tk.Event) -> None:
            if event.widget is window:
                self._clear_text_tool_window(st, window)

        window.bind("<Destroy>", on_destroy, add="+")

    def _update_tab_title(self, st):
        frame = st.get("frame")
        if frame is None:
            return
        try:
            tab = str(frame)
            if tab not in self.nb.tabs():
                return
        except tk.TclError:
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
        if st.get("stream_stop_event") is not None:
            self._interrupt_stream_for_tab(frame)
        if frame == self._log_tab_frame:
            self._log_tab_frame = None
        self.nb.forget(cur)
        self.tabs.pop(frame, None)
        if not self.tabs:
            self._new_tab()

    def _select_tab_by_index(self, index: int) -> None:
        tabs = self.nb.tabs()
        if index < 0 or index >= len(tabs):
            return
        self.nb.select(tabs[index])

    def _select_tab_by_offset(self, offset: int) -> None:
        tabs = self.nb.tabs()
        if not tabs:
            return
        try:
            cur_index = tabs.index(self.nb.select())
        except ValueError:
            return
        next_index = (cur_index + offset) % len(tabs)
        self.nb.select(tabs[next_index])

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
            accelerator="Ctrl+Shift+Z",
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
        editmenu.add_command(
            label="BOL Tool…", accelerator="Ctrl+B", command=self._open_bol_tool
        )
        editmenu.add_separator()
        editmenu.add_command(
            label="Settings…", accelerator="Ctrl+G", command=self._open_settings
        )
        menubar.add_cascade(label="Edit", menu=editmenu)

        togglemenu = tk.Menu(menubar, tearoff=0)
        self._wrap_menu_var = tk.BooleanVar(value=True)
        togglemenu.add_checkbutton(
            label="Wrap",
            accelerator="Alt+W",
            variable=self._wrap_menu_var,
            command=self._on_wrap_menu_toggled,
        )
        self._follow_menu_var = tk.BooleanVar(
            value=self.cfg.get("follow_stream_enabled", True)
        )
        togglemenu.add_checkbutton(
            label="Follow Stream",
            accelerator="Alt+F",
            variable=self._follow_menu_var,
            command=self._on_follow_menu_toggled,
        )
        self._line_numbers_menu_var = tk.BooleanVar(
            value=self.cfg.get("line_numbers_enabled", False)
        )
        togglemenu.add_checkbutton(
            label="Line Numbers",
            accelerator="Alt+N",
            variable=self._line_numbers_menu_var,
            command=self._toggle_line_numbers,
        )
        self._spell_menu_var = tk.BooleanVar(value=self.cfg.get("spellcheck_enabled", True))
        togglemenu.add_checkbutton(
            label="Spellcheck",
            accelerator="Alt+S",
            variable=self._spell_menu_var,
            command=self._toggle_spellcheck,
        )
        menubar.add_cascade(label="Toggle", menu=togglemenu)

        aimenu = tk.Menu(menubar, tearoff=0)
        aimenu.add_command(
            label="Generate",
            accelerator="Alt+G",
            command=self.generate,
        )
        aimenu.add_command(
            label="Repeat Last FIM",
            accelerator="Alt+R",
            command=self.repeat_last_fim,
        )
        aimenu.add_command(
            label="Paste Last FIM Tag",
            accelerator="Alt+P",
            command=self.paste_last_fim_tag,
        )
        aimenu.add_command(
            label="Apply Config Tag",
            accelerator="Alt+C",
            command=self.apply_config_tag,
        )
        aimenu.add_command(
            label="Paste Current Config",
            accelerator="Alt+J",
            command=self.paste_current_config,
        )
        aimenu.add_command(
            label="Interrupt Stream",
            accelerator="Alt+I",
            command=self.interrupt_stream,
        )
        aimenu.add_command(
            label="Validate Tags",
            accelerator="Alt+V",
            command=self.validate_tags_current,
        )
        aimenu.add_command(
            label="Show Log",
            accelerator="Alt+L",
            command=self.show_fim_log,
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
        with contextlib.suppress(TypeError, ValueError):
            st["last_yview"] = float(first)
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
        with contextlib.suppress(Exception):
            st["last_yview"] = float(st["text"].yview()[0])
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

    def _event_on_current_text(self, sequence: str) -> None:
        st = self._current_tab_state()
        if not st:
            return
        text = st.get("text")
        if text is not None:
            text.event_generate(sequence)

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
        self._persist_config()
        if self._follow_menu_var is not None:
            self._follow_menu_var.set(enabled)
        for st in self.tabs.values():
            if not enabled:
                st["stream_following"] = False
                st["_stream_follow_primed"] = False
                self._cancel_stream_follow_job(st)
            elif st.get("stream_active"):
                st["stream_following"] = True

    def _toggle_line_numbers(self):
        enabled = not self.cfg.get("line_numbers_enabled", False)
        self.cfg["line_numbers_enabled"] = enabled
        self._persist_config()
        if self._line_numbers_menu_var is not None:
            self._line_numbers_menu_var.set(enabled)
        for st in self.tabs.values():
            self._apply_line_numbers_state(st, enabled)
            self._schedule_line_number_update(st["frame"], delay_ms=10)

    def _toggle_spellcheck(self):
        enabled = not self.cfg.get("spellcheck_enabled", True)
        self.cfg["spellcheck_enabled"] = enabled
        self._persist_config()
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

    def _show_error(
        self,
        title: str,
        message: str,
        detail: str | None = None,
        parent: tk.Misc | None = None,
        copy_label: str = "Copy error message",
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)

        message_label = ttk.Label(frame, text=message, justify="left", wraplength=480)
        message_label.grid(row=0, column=0, columnspan=2, sticky="w")

        row = 1
        if detail:
            detail_font = (
                self.app_font.cget("family"),
                self.app_font.cget("size"),
                "bold",
            )
            detail_label = ttk.Label(frame, text="Details:", font=detail_font)
            detail_label.grid(row=row, column=0, sticky="nw", pady=(10, 2))

            detail_text = tk.Text(
                frame,
                height=6,
                width=60,
                wrap="word",
                state="normal",
                background=self.cget("background"),
                relief=tk.SOLID,
                borderwidth=1,
            )
            detail_text.insert("1.0", detail)
            detail_text.config(state="disabled")
            detail_text.grid(row=row + 1, column=0, columnspan=2, sticky="nsew")
            row += 2

        def _copy_error_message() -> None:
            clip_text = message if detail is None else f"{message}\n\nDetails: {detail}"
            try:
                self.clipboard_clear()
                self.clipboard_append(clip_text)
            except tk.TclError:
                pass

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, pady=(12, 0), sticky="e")

        copy_btn = ttk.Button(buttons, text=copy_label, command=_copy_error_message)
        copy_btn.grid(row=0, column=0, padx=(0, 8))

        ok_btn = ttk.Button(buttons, text="OK", command=dialog.destroy)
        ok_btn.grid(row=0, column=1)
        ok_btn.focus_set()

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self._prepare_child_window(dialog, parent)
        self.wait_window(dialog)

    def _show_message(
        self,
        title: str,
        message: str,
        detail: str | None = None,
        parent: tk.Misc | None = None,
    ) -> None:
        self._show_error(
            title,
            message,
            detail=detail,
            parent=parent,
            copy_label="Copy message",
        )

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
        reuse_target = st if st and not self._is_log_tab(st) else None
        if reuse_target and not self._maybe_save(reuse_target):
            return
        path = self._open_file_dialog()
        if not path:
            return
        if reuse_target is None or not self._can_reuse_tab_for_open(reuse_target):
            reuse_target = self._new_tab()
        self._load_file_into_tab(reuse_target, path)

    def _open_file_dialog(self, initial_dir: str | None = None) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title("Open File")
        dialog.geometry("900x700")
        self._prepare_child_window(dialog)
        dialog.grab_set()

        current_dir = os.path.abspath(initial_dir or os.getcwd())
        show_hidden = tk.BooleanVar(value=False)
        selected_path: str | None = None
        open_btn: ttk.Button | None = None

        path_var = tk.StringVar(value=current_dir)

        def refresh_dir(path: str) -> None:
            nonlocal current_dir, selected_path
            try:
                entries = list(os.scandir(path))
            except OSError as exc:
                self._show_error("Open Error", "Could not list directory.", detail=str(exc))
                return

            current_dir = os.path.abspath(path)
            path_var.set(current_dir)
            tree.delete(*tree.get_children())
            item_paths.clear()
            selected_path = None
            if open_btn:
                open_btn.config(state=tk.DISABLED)

            visible_entries: list[os.DirEntry[str]] = []
            for entry in entries:
                if not show_hidden.get() and entry.name.startswith("."):
                    continue
                visible_entries.append(entry)

            def sort_key(ent: os.DirEntry[str]) -> tuple[int, str]:
                return (0 if ent.is_dir(follow_symlinks=False) else 1, ent.name.lower())

            for entry in sorted(visible_entries, key=sort_key):
                item_id = tree.insert("", tk.END, text=entry.name)
                item_paths[item_id] = entry.path
                if entry.is_dir(follow_symlinks=False):
                    tree.item(item_id, values=("dir",))

            tree.yview_moveto(0)

        def on_select(_event=None) -> None:
            nonlocal selected_path
            selection = tree.selection()
            item = selection[0] if selection else tree.focus()
            selected_path = item_paths.get(item)
            open_btn_state = (
                tk.NORMAL if selected_path and os.path.isfile(selected_path) else tk.DISABLED
            )
            open_btn.config(state=open_btn_state)

        def open_selection(_event=None) -> None:
            nonlocal selected_path
            selection = tree.selection()
            item = selection[0] if selection else tree.focus()
            chosen = item_paths.get(item)
            if not chosen:
                return
            if os.path.isdir(chosen):
                refresh_dir(chosen)
                return
            selected_path = chosen
            dialog.destroy()

        def go_parent() -> None:
            refresh_dir(os.path.dirname(current_dir) or current_dir)

        def toggle_hidden() -> None:
            refresh_dir(current_dir)

        def create_directory() -> None:
            name = simpledialog.askstring("Create Directory", "Directory name:", parent=dialog)
            if not name:
                return
            new_path = os.path.join(current_dir, name)
            try:
                os.makedirs(new_path, exist_ok=False)
            except OSError as exc:
                self._show_error(
                    "Create Directory Error",
                    "Could not create directory.",
                    detail=str(exc),
                )
                return
            refresh_dir(new_path)
            try:
                for item_id, path in item_paths.items():
                    if path == new_path:
                        tree.focus(item_id)
                        tree.selection_set(item_id)
                        break
            except tk.TclError:
                pass

        header = ttk.Frame(dialog, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Current directory:").grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(header, textvariable=path_var, state="readonly")
        path_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(header, text="Go To Parent Dir", command=go_parent).grid(
            row=0, column=2, sticky="e"
        )

        controls = ttk.Frame(dialog, padding=(12, 0, 12, 6))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)

        hidden_btn = ttk.Checkbutton(
            controls, text="Show hidden files", variable=show_hidden, command=toggle_hidden
        )
        hidden_btn.grid(row=0, column=0, sticky="w")
        ttk.Button(controls, text="Create New Dir", command=create_directory).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )

        list_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        list_frame.grid(row=2, column=0, sticky="nsew")
        dialog.rowconfigure(2, weight=1)
        dialog.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        tree_style = ttk.Style(dialog)
        dialog_font = tkfont.nametofont("TkDefaultFont")
        row_height = max(dialog_font.metrics("linespace") + 6, 22)
        tree_style.configure(
            "OpenDialog.Treeview", font=dialog_font, rowheight=row_height
        )

        tree = ttk.Treeview(
            list_frame,
            columns=("kind",),
            show="tree",
            selectmode="browse",
            style="OpenDialog.Treeview",
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        item_paths: dict[str, str] = {}

        def on_mousewheel(event: tk.Event) -> None:
            delta = 0
            if hasattr(event, "delta") and event.delta:
                delta = int(-event.delta / 120)
            elif event.num == 4:
                delta = -1
            elif event.num == 5:
                delta = 1
            if delta:
                tree.yview_scroll(delta, "units")
                return "break"

        tree.bind("<MouseWheel>", on_mousewheel)
        tree.bind("<Button-4>", on_mousewheel)
        tree.bind("<Button-5>", on_mousewheel)
        tree.bind("<Double-1>", open_selection)
        tree.bind("<Return>", open_selection)
        tree.bind("<<TreeviewSelect>>", on_select)

        buttons = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        buttons.grid(row=3, column=0, sticky="e")
        buttons.columnconfigure(0, weight=1)

        def cancel_dialog() -> None:
            nonlocal selected_path
            selected_path = None
            dialog.destroy()

        open_btn = ttk.Button(buttons, text="Open", command=open_selection, state=tk.DISABLED)
        open_btn.grid(row=0, column=0, padx=(0, 8))
        cancel_btn = ttk.Button(buttons, text="Cancel", command=cancel_dialog)
        cancel_btn.grid(row=0, column=1)

        refresh_dir(current_dir)
        tree.focus_set()
        dialog.protocol("WM_DELETE_WINDOW", cancel_dialog)
        self.wait_window(dialog)

        if selected_path and os.path.isfile(selected_path):
            return selected_path
        return None

    def _save_file_dialog(
        self, initial_dir: str | None = None, default_name: str | None = None
    ) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title("Save File")
        dialog.geometry("900x760")
        self._prepare_child_window(dialog)
        dialog.grab_set()

        current_dir = os.path.abspath(initial_dir or os.getcwd())
        show_hidden = tk.BooleanVar(value=False)
        filename_var = tk.StringVar(value=default_name or "")
        save_btn: ttk.Button | None = None

        path_var = tk.StringVar(value=current_dir)

        item_paths: dict[str, str] = {}

        def update_save_state(*_args: object) -> None:
            if not save_btn:
                return
            name = filename_var.get().strip()
            save_btn_state = tk.NORMAL if name else tk.DISABLED
            save_btn.config(state=save_btn_state)

        def refresh_dir(path: str) -> None:
            nonlocal current_dir
            try:
                entries = list(os.scandir(path))
            except OSError as exc:
                self._show_error("Save Error", "Could not list directory.", detail=str(exc))
                return

            current_dir = os.path.abspath(path)
            path_var.set(current_dir)
            tree.delete(*tree.get_children())
            item_paths.clear()
            update_save_state()

            visible_entries: list[os.DirEntry[str]] = []
            for entry in entries:
                if not show_hidden.get() and entry.name.startswith("."):
                    continue
                visible_entries.append(entry)

            def sort_key(ent: os.DirEntry[str]) -> tuple[int, str]:
                return (0 if ent.is_dir(follow_symlinks=False) else 1, ent.name.lower())

            for entry in sorted(visible_entries, key=sort_key):
                item_id = tree.insert("", tk.END, text=entry.name)
                item_paths[item_id] = entry.path
                if entry.is_dir(follow_symlinks=False):
                    tree.item(item_id, values=("dir",))

            tree.yview_moveto(0)

        def on_select(_event=None) -> None:
            selection = tree.selection()
            item = selection[0] if selection else tree.focus()
            chosen = item_paths.get(item)
            if chosen and os.path.isfile(chosen):
                filename_var.set(os.path.basename(chosen))
            update_save_state()

        def open_selection(_event=None) -> None:
            selection = tree.selection()
            item = selection[0] if selection else tree.focus()
            chosen = item_paths.get(item)
            if not chosen:
                return
            if os.path.isdir(chosen):
                refresh_dir(chosen)
                return
            filename_var.set(os.path.basename(chosen))
            save_selection()

        def go_parent() -> None:
            refresh_dir(os.path.dirname(current_dir) or current_dir)

        def toggle_hidden() -> None:
            refresh_dir(current_dir)

        def create_directory() -> None:
            name = simpledialog.askstring("Create Directory", "Directory name:", parent=dialog)
            if not name:
                return
            new_path = os.path.join(current_dir, name)
            try:
                os.makedirs(new_path, exist_ok=False)
            except OSError as exc:
                self._show_error(
                    "Create Directory Error",
                    "Could not create directory.",
                    detail=str(exc),
                )
                return
            refresh_dir(new_path)
            try:
                for item_id, path in item_paths.items():
                    if path == new_path:
                        tree.focus(item_id)
                        tree.selection_set(item_id)
                        break
            except tk.TclError:
                pass

        def save_selection(_event=None) -> None:
            name = filename_var.get().strip()
            if not name:
                return
            dialog.selected_path = os.path.join(current_dir, name)  # type: ignore[attr-defined]
            dialog.destroy()

        header = ttk.Frame(dialog, padding=(12, 12, 12, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Current directory:").grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(header, textvariable=path_var, state="readonly")
        path_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(header, text="Go To Parent Dir", command=go_parent).grid(
            row=0, column=2, sticky="e"
        )

        controls = ttk.Frame(dialog, padding=(12, 0, 12, 6))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)

        hidden_btn = ttk.Checkbutton(
            controls, text="Show hidden files", variable=show_hidden, command=toggle_hidden
        )
        hidden_btn.grid(row=0, column=0, sticky="w")
        ttk.Button(controls, text="Create New Dir", command=create_directory).grid(
            row=0, column=1, sticky="e", padx=(8, 0)
        )

        name_frame = ttk.Frame(dialog, padding=(12, 0, 12, 6))
        name_frame.grid(row=2, column=0, sticky="ew")
        name_frame.columnconfigure(1, weight=1)

        ttk.Label(name_frame, text="File name:").grid(row=0, column=0, sticky="w")
        name_entry = ttk.Entry(name_frame, textvariable=filename_var)
        name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        name_entry.bind("<Return>", save_selection)

        list_frame = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        list_frame.grid(row=3, column=0, sticky="nsew")
        dialog.rowconfigure(3, weight=1)
        dialog.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        tree_style = ttk.Style(dialog)
        dialog_font = tkfont.nametofont("TkDefaultFont")
        row_height = max(dialog_font.metrics("linespace") + 6, 22)
        tree_style.configure(
            "SaveDialog.Treeview", font=dialog_font, rowheight=row_height
        )

        tree = ttk.Treeview(
            list_frame,
            columns=("kind",),
            show="tree",
            selectmode="browse",
            style="SaveDialog.Treeview",
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        def on_mousewheel(event: tk.Event) -> None:
            delta = 0
            if hasattr(event, "delta") and event.delta:
                delta = int(-event.delta / 120)
            elif event.num == 4:
                delta = -1
            elif event.num == 5:
                delta = 1
            if delta:
                tree.yview_scroll(delta, "units")
                return "break"

        tree.bind("<MouseWheel>", on_mousewheel)
        tree.bind("<Button-4>", on_mousewheel)
        tree.bind("<Button-5>", on_mousewheel)
        tree.bind("<Double-1>", open_selection)
        tree.bind("<Return>", open_selection)
        tree.bind("<<TreeviewSelect>>", on_select)

        buttons = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        buttons.grid(row=4, column=0, sticky="e")
        buttons.columnconfigure(0, weight=1)

        save_btn = ttk.Button(buttons, text="Save", command=save_selection, state=tk.DISABLED)
        save_btn.grid(row=0, column=0, padx=(0, 8))
        cancel_btn = ttk.Button(buttons, text="Cancel", command=dialog.destroy)
        cancel_btn.grid(row=0, column=1)

        filename_var.trace_add("write", update_save_state)
        refresh_dir(current_dir)
        update_save_state()
        name_entry.focus_set()
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.wait_window(dialog)

        selected_path: str | None = getattr(dialog, "selected_path", None)
        if selected_path:
            return os.path.abspath(selected_path)
        return None

    def _can_reuse_tab_for_open(self, st: dict) -> bool:
        if st.get("dirty") or st.get("path") or st.get("is_log_tab"):
            return False
        text: tk.Text | None = st.get("text")
        if not text:
            return False
        return text.get("1.0", "end-1c") == ""

    def _load_file_into_tab(self, st: dict, path: str) -> bool:
        normalized = os.path.abspath(os.path.expanduser(path))
        try:
            with open(normalized, encoding="utf-8") as f:
                data = f.read()
            st["suppress_modified"] = True
            st["text"].delete("1.0", tk.END)
            st["text"].insert("1.0", data)
            st["text"].mark_set("insert", "1.0")
            st["text"].focus_set()
            st["text"].edit_modified(False)
            st["suppress_modified"] = False
            st["path"] = normalized
            self._set_dirty(st, False)
            frame = st.get("frame") or self.nb.select()
            self._schedule_spellcheck_for_frame(frame, delay_ms=200)
            self._schedule_line_number_update(frame, delay_ms=10)
            return True
        except Exception as e:
            self._show_error("Open Error", "Could not open the file.", detail=str(e))
            return False

    def open_files(self, paths: Iterable[str]) -> None:
        path_list = [os.path.abspath(os.path.expanduser(p)) for p in paths if p]
        if not path_list:
            return

        reuse_current = True
        for path in path_list:
            st = None
            if reuse_current:
                current = self._current_tab_state()
                if current and self._can_reuse_tab_for_open(current):
                    st = current
                reuse_current = False
            if st is None:
                st = self._new_tab()
            if not st:
                continue
            self._load_file_into_tab(st, path)

    def _save_file_current(self):
        st = self._current_tab_state()
        if not st:
            return
        path = st["path"]
        if not path:
            return self._save_file_as_current()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(st["text"].get("1.0", "end-1c"))
            st["text"].edit_modified(False)
            self._set_dirty(st, False)
        except Exception as e:
            self._show_error("Save Error", "Could not save the file.", detail=str(e))

    def _save_file_as_current(self):
        st = self._current_tab_state()
        if not st:
            return
        current_path = st.get("path")
        initial_dir = os.path.dirname(current_path) if current_path else None
        default_name = os.path.basename(current_path) if current_path else "Untitled.txt"
        path = self._save_file_dialog(initial_dir=initial_dir, default_name=default_name)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(st["text"].get("1.0", "end-1c"))
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

        self._destroy_text_tool_window(st)

        w = tk.Toplevel(self)
        w.title("Find & Replace")
        w.resizable(False, False)
        container = ttk.Frame(w, padding=8)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text="Find:").grid(row=0, column=0, padx=0, pady=8, sticky="e")
        ttk.Label(container, text="Replace:").grid(
            row=1, column=0, padx=0, pady=8, sticky="e"
        )
        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        e1 = ttk.Entry(container, width=42, textvariable=find_var)
        e2 = ttk.Entry(container, width=42, textvariable=repl_var)
        e1.grid(row=0, column=1, padx=(8, 0), pady=8, sticky="ew")
        e2.grid(row=1, column=1, padx=(8, 0), pady=8, sticky="ew")
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

        def select_match(start: str, end: str) -> None:
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_remove(match_tag, "1.0", tk.END)
            text.tag_add("sel", start, end)
            text.tag_add(match_tag, start, end)

        def find_previous():
            patt = find_var.get()
            if not patt:
                clear_highlight()
                return
            ranges = text.tag_ranges(match_tag)
            if ranges:
                start = ranges[0]
                start_search = start if text.compare(start, "==", "1.0") else f"{start}-1c"
            else:
                start_search = text.index(tk.INSERT)
            pos = text.search(patt, start_search, stopindex="1.0", backwards=True)
            if not pos:
                pos = text.search(patt, tk.END, stopindex="1.0", backwards=True)
                if not pos:
                    clear_highlight()
                    set_status("Not found.")
                    return
            end = f"{pos}+{len(patt)}c"
            select_match(pos, end)
            text.mark_set(tk.INSERT, end)
            text.see(pos)
            set_status("")
            update_buttons()

        def find_next():
            patt = find_var.get()
            if not patt:
                clear_highlight()
                return
            ranges = text.tag_ranges(match_tag)
            start = ranges[1] if ranges else text.index(tk.INSERT)
            pos = text.search(patt, start, stopindex=tk.END)
            if not pos:
                pos = text.search(patt, "1.0", stopindex=tk.END)
                if not pos:
                    clear_highlight()
                    set_status("Not found.")
                    return
            end = f"{pos}+{len(patt)}c"
            select_match(pos, end)
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

        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=2, column=1, padx=(8, 0), pady=6, sticky="ew")
        btn_frame.columnconfigure((0, 1, 2, 3), weight=1)

        ttk.Button(btn_frame, text="Find Previous", command=find_previous).grid(
            row=0, column=0, padx=(0, 4), sticky="w"
        )
        ttk.Button(btn_frame, text="Find", command=find_next).grid(
            row=0, column=1, padx=(0, 4), sticky="w"
        )
        replace_btn = ttk.Button(btn_frame, text="Replace", command=replace_current)
        replace_btn.grid(row=0, column=2)
        replace_all_btn = ttk.Button(btn_frame, text="Replace All", command=replace_all)
        replace_all_btn.grid(row=0, column=3, padx=(4, 0), sticky="e")
        update_buttons()

        status = ttk.Label(container, textvariable=status_var, anchor="w")
        status.grid(
            row=3, column=0, columnspan=2, padx=0, pady=(0, 8), sticky="ew"
        )

        def close_dialog() -> None:
            clear_highlight()
            w.destroy()

        def on_destroy(event: tk.Event) -> None:
            if event.widget is w:
                clear_highlight()
                self._clear_text_tool_window(st, w)

        self._prepare_child_window(w)
        w.bind("<Destroy>", on_destroy, add="+")
        w.protocol("WM_DELETE_WINDOW", close_dialog)
        self._track_text_tool_window(st, w, "replace")

    def _open_regex_replace_dialog(self):
        st = self._current_tab_state()
        if not st:
            return
        text = st["text"]

        self._destroy_text_tool_window(st)

        w = tk.Toplevel(self)
        w.title("Regex Find & Replace")
        w.resizable(False, False)

        container = ttk.Frame(w, padding=8)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(1, weight=1)

        ttk.Label(container, text="Pattern (Python regex):").grid(
            row=0, column=0, padx=0, pady=8, sticky="e"
        )
        ttk.Label(container, text="Replacement:").grid(
            row=1, column=0, padx=0, pady=8, sticky="e"
        )
        find_var = tk.StringVar()
        repl_var = tk.StringVar()
        ignorecase_var = tk.BooleanVar(value=False)
        multiline_var = tk.BooleanVar(value=False)
        dotall_var = tk.BooleanVar(value=False)
        e1 = ttk.Entry(container, width=42, textvariable=find_var)
        e2 = ttk.Entry(container, width=42, textvariable=repl_var)
        e1.grid(row=0, column=1, padx=(8, 0), pady=8, sticky="ew")
        e2.grid(row=1, column=1, padx=(8, 0), pady=8, sticky="ew")
        e1.focus_set()

        flag_frame = ttk.Frame(container)
        flag_frame.grid(row=2, column=0, columnspan=2, padx=0, sticky="w")
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
                self._show_error(
                    "Regex Error", "Invalid regex.", detail=str(exc), parent=w
                )
                update_buttons()
                return None

        def highlight_match(
            content: str,
            match: re.Match[str],
            wrapped: bool,
            status_msg: str | None = None,
        ) -> None:
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
            if status_msg is not None:
                set_status(status_msg)
            elif wrapped:
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

        def find_previous():
            pattern = get_pattern()
            if not pattern:
                return
            content = text.get("1.0", tk.END)
            ranges = text.tag_ranges(match_tag)
            if ranges:
                start_offset = len(text.get("1.0", ranges[0]))
            else:
                start_offset = len(text.get("1.0", tk.INSERT))

            prev_match: re.Match[str] | None = None
            if start_offset > 0:
                for match in pattern.finditer(content, 0, start_offset):
                    prev_match = match
            wrapped = False
            if prev_match is None:
                for match in pattern.finditer(content):
                    prev_match = match
                if prev_match is None:
                    clear_highlight(reset_status=False)
                    set_status("No matches found.")
                    update_buttons()
                    return
                wrapped = True

            status_msg = "Wrapped to the end; continuing search." if wrapped else ""
            highlight_match(content, prev_match, wrapped, status_msg=status_msg)

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
                self._show_error(
                    "Regex Error", "Replacement failed.", detail=str(exc), parent=w
                )
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
                self._show_error(
                    "Regex Error", "Replacement failed.", detail=str(exc), parent=w
                )
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

        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=3, column=1, padx=(8, 0), pady=6, sticky="ew")
        btn_frame.columnconfigure((0, 1, 2, 3), weight=1)

        ttk.Button(btn_frame, text="Find previous", command=find_previous).grid(
            row=0, column=0, padx=(0, 4), sticky="w"
        )
        ttk.Button(btn_frame, text="Find next", command=find_next).grid(
            row=0, column=1, padx=(0, 4), sticky="w"
        )
        replace_btn = ttk.Button(btn_frame, text="Replace", command=replace_current)
        replace_btn.grid(row=0, column=2)
        replace_all_btn = ttk.Button(btn_frame, text="Replace all", command=replace_all)
        replace_all_btn.grid(row=0, column=3)
        update_buttons()

        status = ttk.Label(container, textvariable=status_var, anchor="w")
        status.grid(row=4, column=0, columnspan=2, padx=0, pady=(0, 8), sticky="ew")

        def on_close() -> None:
            clear_highlight()
            w.destroy()

        def on_destroy(event: tk.Event) -> None:
            if event.widget is w:
                clear_highlight()
                self._clear_text_tool_window(st, w)

        w.protocol("WM_DELETE_WINDOW", on_close)
        w.bind("<Destroy>", on_destroy, add="+")
        self._prepare_child_window(w)
        self._track_text_tool_window(st, w, "regex_replace")

    def _open_bol_tool(self, event=None):
        st = self._current_tab_state()
        if not st or self._is_log_tab(st):
            return
        text = st.get("text")
        if text is None:
            return

        self._destroy_text_tool_window(st)

        try:
            original_sel: tuple[str, str] | None = (
                text.index("sel.first"),
                text.index("sel.last"),
            )
        except tk.TclError:
            original_sel = None

        original_content = text.get("1.0", "end-1c")
        original_dirty = st.get("dirty", False)
        original_insert = text.index(tk.INSERT)
        original_yview = text.yview()
        def selected_line_range() -> tuple[int, int]:
            try:
                start_idx = text.index("sel.first")
                end_idx = text.index("sel.last")
            except tk.TclError:
                line_idx = text.index(tk.INSERT)
                line_num = int(line_idx.split(".")[0])
                return line_num, line_num

            start_line = int(text.index(f"{start_idx} linestart").split(".")[0])
            try:
                end_target = text.index(f"{end_idx} -1c")
            except tk.TclError:
                end_target = end_idx
            end_line = int(text.index(f"{end_target} linestart").split(".")[0])
            return start_line, end_line

        def get_selected_lines() -> tuple[int, int, list[str]]:
            start_line, end_line = selected_line_range()
            lines = [
                text.get(f"{line}.0", f"{line}.0 lineend")
                for line in range(start_line, end_line + 1)
            ]
            return start_line, end_line, lines

        def apply_transformation(transform: Callable[[list[str]], list[str]]) -> None:
            start_line, end_line, lines = get_selected_lines()
            yview = text.yview()
            insert_idx = text.index(tk.INSERT)
            new_lines = transform(list(lines))
            if new_lines is None or len(new_lines) != len(lines):
                return
            text.edit_separator()
            for offset, new_line in enumerate(new_lines):
                target_line = start_line + offset
                line_start = f"{target_line}.0"
                line_end = f"{target_line}.0 lineend"
                text.delete(line_start, line_end)
                text.insert(line_start, new_line)
            text.edit_separator()
            sel_start = f"{start_line}.0"
            sel_end = f"{end_line}.0 lineend"
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_add("sel", sel_start, sel_end)
            with contextlib.suppress(Exception):
                text.yview_moveto(yview[0])
            text.mark_set(tk.INSERT, insert_idx)
            text.see(sel_start)
            text.focus_set()
            self._schedule_line_number_update(st["frame"], delay_ms=10)

        start_line, end_line = selected_line_range()
        text.tag_remove("sel", "1.0", tk.END)
        text.tag_add("sel", f"{start_line}.0", f"{end_line}.0 lineend")
        text.see(f"{start_line}.0")

        w = tk.Toplevel(self)
        w.title("BOL Tool")
        w.resizable(False, False)

        indent_size_var = tk.StringVar(value="4")
        prefix_var = tk.StringVar(value="")
        delete_count_var = tk.StringVar(value="1")
        skip_empty_var = tk.BooleanVar(value=False)

        def _clamp_bol_value(var: tk.StringVar) -> int:
            try:
                value = int(var.get())
            except ValueError:
                value = 1

            value = max(1, min(8, value))
            var.set(str(value))
            return value

        def indent_size() -> int:
            return _clamp_bol_value(indent_size_var)

        def delete_count() -> int:
            return _clamp_bol_value(delete_count_var)

        def clear_changes() -> None:
            text.edit_separator()
            st["suppress_modified"] = True
            text.delete("1.0", tk.END)
            text.insert("1.0", original_content)
            text.edit_modified(False)
            st["suppress_modified"] = False
            self._set_dirty(st, original_dirty)
            text.mark_set(tk.INSERT, original_insert)
            with contextlib.suppress(Exception):
                text.yview_moveto(original_yview[0])
            text.tag_remove("sel", "1.0", tk.END)
            if original_sel:
                text.tag_add("sel", original_sel[0], original_sel[1])
            self._schedule_line_number_update(st["frame"], delay_ms=10)

        def cancel_dialog() -> None:
            clear_changes()
            w.destroy()

        controls = ttk.Frame(w, padding=12)
        controls.grid(row=0, column=0, sticky="nsew")
        w.columnconfigure(0, weight=1)

        button_width = 14

        ttk.Label(controls, text="Indent size:").grid(row=0, column=0, sticky="e", padx=(0, 6))
        indent_combo = ttk.Combobox(
            controls,
            values=[str(i) for i in range(1, 9)],
            textvariable=indent_size_var,
            width=4,
            exportselection=False,
        )
        indent_combo.grid(row=0, column=1, sticky="w")
        indent_combo.bind("<<ComboboxSelected>>", lambda _e: indent_size())
        indent_combo.bind("<FocusOut>", lambda _e: indent_size())
        indent_combo.bind("<Return>", lambda _e: indent_size())

        ttk.Button(
            controls,
            text="Tabs → Spaces",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _tabs_to_spaces(
                    lines, indent_size(), skip_empty_var.get()
                )
            ),
        ).grid(row=0, column=2, padx=(12, 0), sticky="we")
        ttk.Button(
            controls,
            text="Spaces → Tabs",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _spaces_to_tabs(
                    lines, indent_size(), skip_empty_var.get()
                )
            ),
        ).grid(row=0, column=3, padx=(8, 0), sticky="we")

        ttk.Button(
            controls,
            text="Indent",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _indent_block(
                    lines, indent_size(), skip_empty_var.get()
                )
            ),
        ).grid(row=1, column=2, pady=(10, 0), padx=(12, 0), sticky="we")
        ttk.Button(
            controls,
            text="De-indent",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _deindent_block(
                    lines, indent_size(), skip_empty_var.get()
                )
            ),
        ).grid(row=1, column=3, pady=(10, 0), padx=(8, 0), sticky="we")

        ttk.Label(controls, text="Prepend:").grid(
            row=2, column=0, sticky="e", padx=(0, 6), pady=(10, 0)
        )
        ttk.Entry(controls, textvariable=prefix_var, width=30).grid(
            row=2, column=1, columnspan=2, sticky="we", pady=(10, 0)
        )
        ttk.Button(
            controls,
            text="Prepend",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _prepend_to_lines(
                    lines, prefix_var.get(), skip_empty_var.get()
                )
            ),
        ).grid(row=2, column=3, padx=(8, 0), pady=(10, 0), sticky="we")

        ttk.Label(controls, text="Delete leading:").grid(
            row=3, column=0, sticky="e", padx=(0, 6), pady=(10, 0)
        )
        delete_combo = ttk.Combobox(
            controls,
            values=[str(i) for i in range(1, 9)],
            textvariable=delete_count_var,
            width=4,
            exportselection=False,
        )
        delete_combo.grid(row=3, column=1, sticky="w", pady=(10, 0))
        delete_combo.bind("<<ComboboxSelected>>", lambda _e: delete_count())
        delete_combo.bind("<FocusOut>", lambda _e: delete_count())
        delete_combo.bind("<Return>", lambda _e: delete_count())
        ttk.Button(
            controls,
            text="Delete",
            width=button_width,
            command=lambda: apply_transformation(
                lambda lines: _delete_leading_chars(
                    lines, delete_count(), skip_empty_var.get()
                )
            ),
        ).grid(row=3, column=3, padx=(8, 0), pady=(10, 0), sticky="we")

        ttk.Checkbutton(
            controls,
            text="Do not apply changes to empty lines",
            variable=skip_empty_var,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(12, 0))

        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)
        controls.columnconfigure(3, weight=1)

        btns = ttk.Frame(w, padding=(12, 0, 12, 12))
        btns.grid(row=1, column=0, sticky="ew")
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        btns.columnconfigure(2, weight=1)
        ttk.Button(btns, text="Clear Changes", width=button_width, command=clear_changes).grid(
            row=0, column=0, padx=(0, 8), sticky="we"
        )
        ttk.Button(btns, text="Apply", width=button_width, command=w.destroy).grid(
            row=0, column=1, padx=(0, 8), sticky="we"
        )
        ttk.Button(btns, text="Cancel", width=button_width, command=cancel_dialog).grid(
            row=0, column=2, sticky="we"
        )

        def on_destroy(event: tk.Event) -> None:
            if event.widget is w:
                self._clear_text_tool_window(st, w)

        w.protocol("WM_DELETE_WINDOW", cancel_dialog)
        self._prepare_child_window(w)
        indent_combo.focus_set()
        w.bind("<Destroy>", on_destroy, add="+")
        self._track_text_tool_window(st, w, "bol")

    # ---------- Settings ----------

    def _open_settings(self):
        cfg = self.cfg

        if self._settings_window is not None and self._settings_window.winfo_exists():
            w = self._settings_window
            with contextlib.suppress(tk.TclError):
                w.deiconify()
                w.focus_set()
            self._center_window(w, self)
            self._lift_if_exists(w, self)
            return

        w = tk.Toplevel(self)
        self._settings_window = w
        w.title("Settings — FIMpad")
        w.resizable(True, True)
        w.geometry("720x780")
        w.minsize(520, 600)

        outer = ttk.Frame(w)
        outer.grid(row=0, column=0, sticky="nsew")
        w.columnconfigure(0, weight=1)
        w.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        scroll_bg = outer.cget("background")
        canvas = tk.Canvas(outer, highlightthickness=0, background=scroll_bg)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(canvas, padding=12)
        container_id = canvas.create_window((0, 0), window=container, anchor="nw")
        container.columnconfigure(1, weight=1)

        def _sync_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _resize_inner(event: tk.Event) -> None:
            canvas.itemconfigure(container_id, width=event.width)

        container.bind("<Configure>", _sync_scroll_region, add="+")
        canvas.bind("<Configure>", _resize_inner, add="+")
        w.after_idle(_sync_scroll_region)

        def _on_mousewheel(event: tk.Event) -> None:
            if event.delta:
                canvas.yview_scroll(-int(event.delta / 120), "units")
            elif event.num == 4:
                canvas.yview_scroll(-3, "units")
            elif event.num == 5:
                canvas.yview_scroll(3, "units")

        container.bind("<MouseWheel>", _on_mousewheel, add="+")
        container.bind("<Button-4>", _on_mousewheel, add="+")
        container.bind("<Button-5>", _on_mousewheel, add="+")

        def add_row(r, label, var, width=42):
            ttk.Label(container, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", padx=0, pady=4
            )
            e = ttk.Entry(container, textvariable=var, width=width)
            e.grid(row=r, column=1, padx=(8, 0), pady=4, sticky="ew")
            return e

        def add_combobox_row(r, label, var, values, width=40):
            ttk.Label(container, text=label, anchor="w").grid(
                row=r, column=0, sticky="w", padx=0, pady=4
            )
            cb = ttk.Combobox(container, textvariable=var, values=values, width=width)
            cb.grid(row=r, column=1, padx=(8, 0), pady=4, sticky="w")
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
        spellcheck_debounce_var = tk.StringVar(
            value=str(
                cfg.get(
                    "spellcheck_scroll_debounce_ms",
                    DEFAULTS["spellcheck_scroll_debounce_ms"],
                )
            )
        )
        scroll_speed_var = tk.StringVar(
            value=str(
                cfg.get("scroll_speed_multiplier", DEFAULTS["scroll_speed_multiplier"])
            )
        )
        log_entries_var = tk.StringVar(
            value=str(cfg.get("log_entries_kept", DEFAULTS["log_entries_kept"]))
        )
        stream_follow_debounce_var = tk.StringVar(
            value=str(
                cfg.get(
                    "stream_follow_debounce_ms",
                    DEFAULTS["stream_follow_debounce_ms"],
                )
            )
        )
        fg_var = tk.StringVar(value=cfg["fg"])
        bg_var = tk.StringVar(value=cfg["bg"])
        highlight1_var = tk.StringVar(value=cfg["highlight1"])
        highlight2_var = tk.StringVar(value=cfg["highlight2"])
        open_maximized_var = tk.BooleanVar(value=cfg.get("open_maximized", False))
        reverse_selection_fg_var = tk.BooleanVar(
            value=cfg.get("reverse_selection_fg", DEFAULTS["reverse_selection_fg"])
        )
        spell_lang_var = tk.StringVar(value=self._spell_lang)
        available_spell_langs = self._available_spell_langs
        show_spell_lang = len(available_spell_langs) > 1

        row = 0
        add_row(row, "Endpoint (base, no path):", endpoint_var)
        row += 1
        add_row(row, "Temperature:", temp_var)
        row += 1
        add_row(row, "Top-p:", top_p_var)
        row += 1

        ttk.Checkbutton(
            container,
            text="Open maximized on startup",
            variable=open_maximized_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=0, columnspan=2, padx=0, pady=4, sticky="w")
        row += 1

        ttk.Checkbutton(
            container,
            text="Reverse text color when selected",
            variable=reverse_selection_fg_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=row, column=0, columnspan=2, padx=0, pady=4, sticky="w")
        row += 1

        add_combobox_row(
            row,
            "Scroll speed multiplier:",
            scroll_speed_var,
            [str(v) for v in range(1, 11)],
            width=5,
        )
        row += 1

        add_row(row, "FIM log entries to keep:", log_entries_var, width=8)
        row += 1

        add_row(row, "Stream follow debounce (ms):", stream_follow_debounce_var, width=8)
        row += 1

        add_row(
            row,
            "Spellcheck debounce (ms):",
            spellcheck_debounce_var,
            width=8,
        )
        row += 1

        add_row(row, "Editor padding (px):", pad_var, width=8)
        row += 1

        add_row(row, "Line number padding (px):", line_pad_var, width=8)
        row += 1

        add_row(row, "Font family:", fontfam_var)
        row += 1

        add_row(row, "Font size (6–72):", fontsize_var, width=8)
        row += 1

        add_row(row, "FIM prefix:", fim_pref_var)
        row += 1
        add_row(row, "FIM suffix:", fim_suf_var)
        row += 1
        add_row(row, "FIM middle:", fim_mid_var)
        row += 1

        pad_var.trace_add("write", lambda *_: None)

        def update_line_numbers():
            self._toggle_line_numbers(line_numbers_var.get())

        def update_follow_stream():
            self._toggle_stream_follow(follow_stream_var.get())

        def update_show_button_labels():
            self._toggle_button_labels(show_btn_labels_var.get())

        def update_spellcheck():
            self._toggle_spellcheck(spellcheck_enabled_var.get())

        line_numbers_var = tk.BooleanVar(
            value=cfg.get("line_numbers_enabled", DEFAULTS["line_numbers_enabled"])
        )
        spellcheck_enabled_var = tk.BooleanVar(
            value=cfg.get("spellcheck_enabled", DEFAULTS["spellcheck_enabled"])
        )
        follow_stream_var = tk.BooleanVar(
            value=cfg.get("follow_stream_enabled", DEFAULTS["follow_stream_enabled"])
        )
        show_btn_labels_var = tk.BooleanVar(
            value=cfg.get("show_button_labels", DEFAULTS["show_button_labels"])
        )

        ttk.Checkbutton(
            container,
            text="Follow AI streaming output",
            variable=follow_stream_var,
            onvalue=True,
            offvalue=False,
            command=update_follow_stream,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=4)
        row += 1

        ttk.Checkbutton(
            container,
            text="Enable spellcheck",
            variable=spellcheck_enabled_var,
            onvalue=True,
            offvalue=False,
            command=update_spellcheck,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=4)
        row += 1

        ttk.Checkbutton(
            container,
            text="Show line numbers",
            variable=line_numbers_var,
            onvalue=True,
            offvalue=False,
            command=update_line_numbers,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=4)
        row += 1

        ttk.Checkbutton(
            container,
            text="Show button labels",
            variable=show_btn_labels_var,
            onvalue=True,
            offvalue=False,
            command=update_show_button_labels,
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=4)
        row += 1

        width_for_lines = 64
        otd_actions_var = tk.StringVar(
            value=cfg.get(
                "over_the_line_actions",
                ",".join(DEFAULTS.get("over_the_line_actions", [])),
            )
        )
        line_actions_var = tk.StringVar(
            value=cfg.get(
                "line_actions",
                ",".join(DEFAULTS.get("line_actions", [])),
            )
        )
        stack_actions_var = tk.StringVar(
            value=cfg.get(
                "stack_actions",
                ",".join(DEFAULTS.get("stack_actions", [])),
            )
        )
        base_prompt_var = tk.StringVar(value=cfg.get("base_prompt", ""))
        follow_prompt_var = tk.StringVar(value=cfg.get("follow_prompt", ""))
        config_tags_var = tk.StringVar(value=cfg.get("config_tags", ""))
        config_tag_assignment_var = tk.StringVar(
            value=cfg.get("config_tag_assignment", "")
        )
        config_tag_auto_assign_var = tk.StringVar(
            value=cfg.get("config_tag_auto_assign", "")
        )
        config_tag_default_var = tk.StringVar(value=cfg.get("config_tag_default", ""))

        ttk.Label(
            container, text="""Default over the line actions order (comma separated):"""
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=4)
        row += 1
        ttk.Entry(container, textvariable=otd_actions_var, width=width_for_lines).grid(
            row=row, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we"
        )
        row += 1
        ttk.Label(container, text="Line actions order").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(12, 4)
        )
        ttk.Entry(container, textvariable=line_actions_var, width=width_for_lines).grid(
            row=row, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we"
        )
        row += 1
        ttk.Label(container, text="Stack actions order").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(12, 4)
        )
        ttk.Entry(container, textvariable=stack_actions_var, width=width_for_lines).grid(
            row=row, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we"
        )
        row += 1
        ttk.Label(container, text="Base prompt:").grid(
            row=row, column=0, sticky="w", padx=0, pady=(12, 4)
        )
        ttk.Entry(container, textvariable=base_prompt_var, width=width_for_lines).grid(
            row=row, column=1, padx=(8, 0), pady=(12, 4), sticky="we"
        )
        row += 1
        ttk.Label(container, text="Follow prompt:").grid(
            row=row, column=0, sticky="w", padx=0, pady=(0, 4)
        )
        ttk.Entry(container, textvariable=follow_prompt_var, width=width_for_lines).grid(
            row=row, column=1, padx=(8, 0), pady=(0, 4), sticky="we"
        )
        row += 1

        def pick_color(variable: tk.StringVar, title: str):
            c = colorchooser.askcolor(parent=w, title=title)
            if c and c[1]:
                variable.set(c[1])

        def pick_fg() -> None:
            pick_color(fg_var, "Pick text color")

        def pick_bg() -> None:
            pick_color(bg_var, "Pick background color")

        def pick_highlight1() -> None:
            pick_color(highlight1_var, "Pick caret color")

        def pick_highlight2() -> None:
            pick_color(highlight2_var, "Pick selection color")

        ttk.Label(
            container,
            text="""Config tags (comma-separated words such as 'work', 'relax')""",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 4))
        ttk.Entry(container, textvariable=config_tags_var, width=width_for_lines).grid(
            row=row + 1, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we"
        )
        row += 2
        ttk.Label(
            container,
            text="""Config tag assignment (e.g. 19:relax -> 7pm:relax)""",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 4))
        ttk.Entry(
            container, textvariable=config_tag_assignment_var, width=width_for_lines
        ).grid(row=row + 1, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we")
        row += 2
        ttk.Label(
            container,
            text="""Config tags to apply automatically (comma-separated)
Example: work/7am, 12pm-1pm,
Checks system local time. Empty to disable.""",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 4))
        ttk.Entry(
            container, textvariable=config_tag_auto_assign_var, width=width_for_lines
        ).grid(row=row + 1, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we")
        row += 2
        ttk.Label(
            container,
            text="""Config tags to apply when auto assign is empty (comma-separated)
Example: when working away from home""",
        ).grid(row=row, column=0, columnspan=2, sticky="w", padx=0, pady=(8, 4))
        ttk.Entry(container, textvariable=config_tag_default_var, width=width_for_lines).grid(
            row=row + 1, column=0, columnspan=2, padx=0, pady=(0, 4), sticky="we"
        )
        row += 2

        ttk.Label(container, text="Text color (hex):").grid(
            row=row, column=0, padx=0, pady=4, sticky="w"
        )
        ttk.Entry(container, textvariable=fg_var, width=20).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="w"
        )
        ttk.Button(container, text="Pick…", command=pick_fg).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="e"
        )
        row += 1

        ttk.Label(
            container, text="Background color (hex):"
        ).grid(row=row, column=0, padx=0, pady=4, sticky="w")
        ttk.Entry(container, textvariable=bg_var, width=20).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="w"
        )
        ttk.Button(container, text="Pick…", command=pick_bg).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="e"
        )
        row += 1

        ttk.Label(container, text="Caret color (hex):").grid(
            row=row, column=0, padx=0, pady=4, sticky="w"
        )
        ttk.Entry(container, textvariable=highlight1_var, width=20).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="w"
        )
        ttk.Button(container, text="Pick…", command=pick_highlight1).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="e"
        )
        row += 1

        ttk.Label(container, text="Selection color (hex):").grid(
            row=row, column=0, padx=0, pady=4, sticky="w"
        )
        ttk.Entry(container, textvariable=highlight2_var, width=20).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="w"
        )
        ttk.Button(container, text="Pick…", command=pick_highlight2).grid(
            row=row, column=1, padx=(8, 0), pady=4, sticky="e"
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
            new_cfg = self.cfg.copy()
            prev_pad = new_cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"])
            prev_line_pad = new_cfg.get(
                "line_number_padding_px", DEFAULTS["line_number_padding_px"]
            )
            try:
                new_cfg["endpoint"] = endpoint_var.get().strip().rstrip("/")
                new_cfg["temperature"] = float(temp_var.get())
                new_cfg["top_p"] = float(top_p_var.get())
                new_cfg["fim_prefix"] = fim_pref_var.get()
                new_cfg["fim_suffix"] = fim_suf_var.get()
                new_cfg["fim_middle"] = fim_mid_var.get()
                new_cfg["font_family"] = fontfam_var.get().strip() or DEFAULTS["font_family"]
                new_cfg["font_size"] = max(6, min(72, int(fontsize_var.get())))
                new_cfg["editor_padding_px"] = max(0, int(pad_var.get()))
                new_cfg["line_number_padding_px"] = max(0, int(line_pad_var.get()))
                new_cfg["fg"] = fg_var.get().strip()
                new_cfg["bg"] = bg_var.get().strip()
                new_cfg["highlight1"] = highlight1_var.get().strip()
                new_cfg["highlight2"] = highlight2_var.get().strip()
                new_cfg["open_maximized"] = bool(open_maximized_var.get())
                new_cfg["reverse_selection_fg"] = bool(
                    reverse_selection_fg_var.get()
                )
                new_cfg["scroll_speed_multiplier"] = max(
                    1, min(10, int(scroll_speed_var.get()))
                )
                log_entries_val = int(log_entries_var.get())
                if not 0 <= log_entries_val <= 9999:
                    raise ValueError("log_entries_kept must be between 0 and 9999")
                new_cfg["log_entries_kept"] = log_entries_val
                new_cfg["stream_follow_debounce_ms"] = max(
                    0, int(stream_follow_debounce_var.get())
                )
                new_cfg["spellcheck_scroll_debounce_ms"] = max(
                    0, int(spellcheck_debounce_var.get())
                )
                if show_spell_lang:
                    self._spell_lang = spell_lang_var.get().strip() or DEFAULTS["spell_lang"]
                    new_cfg["spell_lang"] = self._spell_lang
                else:
                    self._spell_lang = DEFAULTS.get("spell_lang", "en_US")
                    new_cfg.pop("spell_lang", None)
            except Exception as e:
                self._show_error(
                    "Settings", "Invalid settings value.", detail=str(e), parent=w
                )
                return

            self._apply_config_changes(
                new_cfg, prev_pad=prev_pad, prev_line_pad=prev_line_pad
            )
            w.destroy()

        def restore_defaults():
            confirmed = messagebox.askyesno(
                "Restore Default Config",
                (
                    "Are you sure you want to restore the default configuration "
                    "setting, overwriting your current settings?"
                ),
                parent=w,
            )
            if not confirmed:
                return

            prev_pad = self.cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"])
            prev_line_pad = self.cfg.get(
                "line_number_padding_px", DEFAULTS["line_number_padding_px"]
            )
            new_cfg = DEFAULTS.copy()
            self._spell_lang = new_cfg.get("spell_lang", DEFAULTS.get("spell_lang", "en_US"))
            self._apply_config_changes(
                new_cfg, prev_pad=prev_pad, prev_line_pad=prev_line_pad
            )
            w.destroy()

        actions = ttk.Frame(container)
        actions.grid(row=row, column=0, columnspan=2, pady=12, sticky="ew")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        ttk.Button(actions, text="Restore Default Config", command=restore_defaults).grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        ttk.Button(actions, text="Save", command=apply_and_close).grid(
            row=0, column=1, padx=(8, 0), sticky="e"
        )

        def _clear_settings_ref(event: tk.Event) -> None:
            if event.widget is w:
                self._settings_window = None

        w.bind("<Destroy>", _clear_settings_ref, add="+")

        self._prepare_child_window(w, parent=self)

    def _apply_config_changes(
        self, new_cfg: dict, *, prev_pad: int, prev_line_pad: int
    ) -> None:
        pad_changed = (
            new_cfg.get("editor_padding_px", prev_pad) != prev_pad
            or new_cfg.get("line_number_padding_px", prev_line_pad)
            != prev_line_pad
        )

        self.cfg = new_cfg
        log_changed = self._apply_log_retention()
        self._persist_config()
        self._apply_open_maximized(self.cfg.get("open_maximized", False))
        line_numbers_enabled = self.cfg.get("line_numbers_enabled", False)
        follow_enabled = self.cfg.get("follow_stream_enabled", True)
        spell_enabled = self.cfg.get("spellcheck_enabled", True)
        if self._line_numbers_menu_var is not None:
            self._line_numbers_menu_var.set(line_numbers_enabled)
        if self._follow_menu_var is not None:
            self._follow_menu_var.set(follow_enabled)
        if self._spell_menu_var is not None:
            self._spell_menu_var.set(spell_enabled)
        self._dictionary = self._load_dictionary(self._spell_lang)
        self.app_font.config(family=self.cfg["font_family"], size=self.cfg["font_size"])

        if log_changed:
            self._refresh_log_tab_contents()

        for frame, st in self.tabs.items():
            t = st["text"]
            st["line_numbers_enabled"] = line_numbers_enabled
            if not follow_enabled:
                st["stream_following"] = False
                st["_stream_follow_primed"] = False
                self._cancel_stream_follow_job(st)
            selection_fg = (
                self.cfg["bg"]
                if self.cfg.get("reverse_selection_fg", False)
                else self.cfg["fg"]
            )
            t.configure(
                font=self.app_font,
                fg=self.cfg["fg"],
                bg=self.cfg["bg"],
                insertbackground=self.cfg["highlight1"],
                selectbackground=self.cfg["highlight2"],
                selectforeground=selection_fg,
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
            if not spell_enabled:
                timer_id = st.get("_spell_timer")
                if timer_id is not None:
                    with contextlib.suppress(Exception):
                        self.after_cancel(timer_id)
                    st["_spell_timer"] = None
                t.tag_remove("misspelled", "1.0", "end")
            else:
                self._schedule_spellcheck_for_frame(frame, delay_ms=200)

    def _fim_tokens_missing(self) -> bool:
        return any(
            not (self.cfg.get(key, "").strip())
            for key in ("fim_prefix", "fim_suffix", "fim_middle")
        )

    def _validate_color_string(self, value: str) -> str:
        color = value.strip()
        if not color:
            raise ValueError("Color value cannot be empty")
        try:
            self.winfo_rgb(color)
        except tk.TclError as exc:  # noqa: BLE001
            raise ValueError(f"Unknown color: {color}") from exc
        return color

    def _font_available(self, font_name: str) -> bool:
        return font_name in set(self._available_font_families())

    def _config_tag_supported_keys(self) -> dict[str, str]:
        return {
            "endpoint": "endpoint",
            "temperature": "temperature",
            "top_p": "top_p",
            "fim_prefix": "fim_prefix",
            "fim_suffix": "fim_suffix",
            "fim_middle": "fim_middle",
            "font_family": "font_family",
            "font_size": "font_size",
            "editor_padding_px": "editor_padding_px",
            "line_number_padding_px": "line_number_padding_px",
            "fg": "fg",
            "bg": "bg",
            "highlight1": "highlight1",
            "highlight2": "highlight2",
            "reverse_selection_fg": "reverse_selection_fg",
            "open_maximized": "open_maximized",
            "scroll_speed_multiplier": "scroll_speed_multiplier",
            "line_numbers_enabled": "line_numbers_enabled",
            "spellcheck_enabled": "spellcheck_enabled",
            "spellcheck_view_buffer_lines": "spellcheck_view_buffer_lines",
            "spellcheck_scroll_debounce_ms": "spellcheck_scroll_debounce_ms",
            "spellcheck_full_document_line_threshold": "spellcheck_full_document_line_threshold",
            "spell_lang": "spell_lang",
            "follow_stream_enabled": "follow_stream_enabled",
            "stream_follow_debounce_ms": "stream_follow_debounce_ms",
            "log_entries_kept": "log_entries_kept",
        }

    def _normalize_config_tag_settings(self, settings: dict[str, object]) -> dict[str, object]:
        supported_keys = self._config_tag_supported_keys()

        alias_map = {k.casefold(): k for k in supported_keys}
        alias_map.update(
            {
                "openmaximized": "open_maximized",
                "reverseselectionfg": "reverse_selection_fg",
                "reversetextcolorwhenselected": "reverse_selection_fg",
            }
        )

        updates: dict[str, object] = {}
        for key, raw_value in settings.items():
            key_cf = key.casefold()
            canonical = alias_map.get(key_cf)
            if canonical is None or canonical not in supported_keys:
                raise ValueError(f"Unknown config key: {key}")

            cfg_key = supported_keys[canonical]
            if cfg_key in updates:
                raise ValueError(f"Duplicate config key: {canonical}")

            try:
                if canonical == "endpoint":
                    if not isinstance(raw_value, str):
                        raise ValueError("endpoint must be a string")
                    updates[cfg_key] = raw_value.strip().rstrip("/")
                elif canonical in {"temperature", "top_p"}:
                    updates[cfg_key] = float(raw_value)
                elif canonical in {"fim_prefix", "fim_suffix", "fim_middle"}:
                    if not isinstance(raw_value, str):
                        raise ValueError(f"{canonical} must be a string")
                    updates[cfg_key] = raw_value
                elif canonical == "font_family":
                    if not isinstance(raw_value, str):
                        raise ValueError("font_family must be a string")
                    font_val = raw_value.strip() or DEFAULTS["font_family"]
                    if not self._font_available(font_val):
                        raise ValueError(f"Font not available: {font_val}")
                    updates[cfg_key] = font_val
                elif canonical == "font_size":
                    updates[cfg_key] = max(6, min(72, int(raw_value)))
                elif canonical in {"editor_padding_px", "line_number_padding_px"}:
                    updates[cfg_key] = max(0, int(raw_value))
                elif canonical in {"fg", "bg", "highlight1", "highlight2"}:
                    if not isinstance(raw_value, str):
                        raise ValueError(f"{canonical} must be a string")
                    updates[cfg_key] = self._validate_color_string(raw_value)
                elif canonical in {
                    "reverse_selection_fg",
                    "open_maximized",
                    "line_numbers_enabled",
                    "spellcheck_enabled",
                    "follow_stream_enabled",
                }:
                    if not isinstance(raw_value, bool):
                        raise ValueError(f"{canonical} must be a boolean")
                    updates[cfg_key] = raw_value
                elif canonical == "scroll_speed_multiplier":
                    updates[cfg_key] = max(1, min(10, int(raw_value)))
                elif canonical in {
                    "spellcheck_view_buffer_lines",
                    "spellcheck_scroll_debounce_ms",
                    "stream_follow_debounce_ms",
                }:
                    updates[cfg_key] = max(0, int(raw_value))
                elif canonical == "spellcheck_full_document_line_threshold":
                    updates[cfg_key] = max(1, int(raw_value))
                elif canonical == "log_entries_kept":
                    log_entries_val = int(raw_value)
                    if not 0 <= log_entries_val <= 9999:
                        raise ValueError("log_entries_kept must be between 0 and 9999")
                    updates[cfg_key] = log_entries_val
                elif canonical == "spell_lang":
                    if not isinstance(raw_value, str):
                        raise ValueError("spell_lang must be a string")
                    lang_val = raw_value.strip() or DEFAULTS.get("spell_lang", "en_US")
                    if lang_val not in self._available_spell_langs:
                        raise ValueError(f"Spellcheck language not available: {lang_val}")
                    updates[cfg_key] = lang_val
            except ValueError as exc:
                raise ValueError(str(exc)) from exc

        return updates

    def _build_current_config_tag(self) -> str:
        supported_keys = self._config_tag_supported_keys()
        cfg = self.__dict__.get("cfg") or {}
        tag_settings = {k: cfg[k] for k in supported_keys if k in cfg}
        lines = ["[[[{"]
        for idx, (key, value) in enumerate(tag_settings.items()):
            comma = "," if idx < len(tag_settings) - 1 else ""
            lines.append(f'"{key}": {json.dumps(value)}{comma}')
        lines.append("}]]]")
        return "\n".join(lines)

    def _apply_config_tag(
        self,
        st: dict,
        tag: ConfigTag,
        *,
        marker_token: TagToken | None = None,
        content: str | None = None,
    ) -> None:
        prev_pad = self.cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"])
        prev_line_pad = self.cfg.get(
            "line_number_padding_px", DEFAULTS["line_number_padding_px"]
        )
        try:
            updates = self._normalize_config_tag_settings(tag.settings)
        except ValueError as exc:
            if marker_token is not None:
                self._highlight_tag_span(
                    st,
                    start=marker_token.start,
                    end=marker_token.end,
                    content=content,
                )
            self._show_error("Config Tag", "Invalid config tag.", detail=str(exc))
            return

        new_cfg = self.cfg.copy()
        new_cfg.update(updates)
        self._spell_lang = new_cfg.get("spell_lang", self._spell_lang)
        self._apply_config_changes(new_cfg, prev_pad=prev_pad, prev_line_pad=prev_line_pad)
        self._show_message("Config Tag", "Settings applied from config tag.", parent=st.get("text"))

    def apply_config_tag(self) -> None:
        st = self._current_tab_state()
        if not st:
            return
        if self._is_log_tab(st):
            return

        text_widget = st.get("text")
        if text_widget is None:
            return

        try:
            cursor_index = text_widget.index(tk.INSERT)
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
            self._highlight_tag_at_cursor(st, content=content, cursor_offset=cursor_offset)
            self._show_error("Config Tag", "Tag could not be parsed.", detail=str(exc))
            return

        guidance = (
            "Place the caret inside or immediately after a config tag to apply it."
        )

        marker_token = self._find_active_tag(tokens, cursor_offset)
        if marker_token is None:
            self._show_message("Config Tag", guidance, parent=text_widget)
            return

        if not isinstance(marker_token.tag, ConfigTag):
            self._highlight_tag_span(
                st,
                start=marker_token.start,
                end=marker_token.end,
                content=content,
            )
            self._show_message("Config Tag", guidance, parent=text_widget)
            return

        self._apply_config_tag(
            st,
            marker_token.tag,
            marker_token=marker_token,
            content=content,
        )

    def paste_current_config(self) -> None:
        st = self._current_tab_state()
        if not st:
            return
        if self._is_log_tab(st):
            return

        text_widget = st.get("text")
        if text_widget is None:
            return

        try:
            cursor_index = text_widget.index(tk.INSERT)
            cursor_offset = int(text_widget.count("1.0", cursor_index, "chars")[0])
        except Exception:
            cursor_offset = None

        content = text_widget.get("1.0", tk.END)
        if cursor_offset is None:
            cursor_offset = len(content)
        cursor_offset = max(0, min(len(content), cursor_offset))

        if self._caret_within_tag(content, cursor_offset):
            self._show_error(
                "Paste Current Config",
                "You cannot paste a config tag when the caret is within a tag.",
            )
            return

        marker = self._build_current_config_tag()

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

    def validate_tags_current(self) -> None:
        st = self._current_tab_state()
        if not st:
            return
        if self._is_log_tab(st):
            return

        text_widget: tk.Text | None = st.get("text")
        if text_widget is None:
            return

        content = text_widget.get("1.0", tk.END)
        tokens: list[TagToken] = []

        for match in TRIPLE_RE.finditer(content):
            body = match.group("body") or ""
            try:
                tag = _parse_tag(body)
            except TagParseError as exc:
                self._highlight_tag_span(
                    st, start=match.start(), end=match.end(), content=content
                )
                self._show_error(
                    "Validate Tags", "Tag could not be parsed.", detail=str(exc)
                )
                return

            tokens.append(
                TagToken(
                    start=match.start(),
                    end=match.end(),
                    raw=match.group(0),
                    body=body,
                    tag=tag,
                )
            )

        self._show_message("Validate Tags", "All tags are valid.", parent=text_widget)

    # ---------- Generate (streaming) ----------

    def _should_follow(self, text_widget: tk.Text) -> bool:
        try:
            _first, last = text_widget.yview()
        except Exception:
            return True
        return last >= 0.999

    def _scroll_log_tab_to_end(self, st: dict) -> None:
        text: tk.Text | None = st.get("text") if st else None
        if text is None:
            return
        st["suppress_modified"] = True
        with contextlib.suppress(tk.TclError):
            text.config(state=tk.NORMAL)
            text.mark_set("insert", tk.END)
            text.see(tk.END)
            text.edit_modified(False)
            text.config(state=tk.DISABLED)
        st["suppress_modified"] = False

    def _stream_follow_enabled(self, st: dict) -> bool:
        cfg = self.__dict__.get("cfg") or {}
        return bool(st.get("stream_active") and cfg.get("follow_stream_enabled", True))

    def _cancel_stream_follow_job(self, st: dict) -> None:
        job = st.get("_stream_follow_job")
        if job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(job)
        st["_stream_follow_job"] = None
        st["_pending_follow_mark"] = None

    def _maybe_follow_stream(self, st: dict, mark: str) -> None:
        text: tk.Text | None = st.get("text") if st else None
        if text is None or not mark:
            return
        if not self._stream_follow_enabled(st):
            st["stream_following"] = False
            st["_stream_follow_primed"] = False
            self._cancel_stream_follow_job(st)
            return

        st["_pending_follow_mark"] = mark
        if st.get("_stream_follow_job") is None:
            frame = st.get("frame")
            cfg = self.__dict__.get("cfg") or {}
            debounce_ms = max(
                0,
                int(
                    cfg.get(
                        "stream_follow_debounce_ms",
                        DEFAULTS["stream_follow_debounce_ms"],
                    )
                ),
            )
            st["_stream_follow_job"] = self.after(
                debounce_ms, lambda fr=frame: self._perform_stream_follow(fr)
            )

    def _perform_stream_follow(self, frame: tk.Misc | None) -> None:
        st = self.tabs.get(frame) if frame else None
        if not st:
            return

        st["_stream_follow_job"] = None
        mark = st.get("_pending_follow_mark")
        st["_pending_follow_mark"] = None
        text: tk.Text | None = st.get("text")
        if text is None or not mark:
            return

        if not self._stream_follow_enabled(st):
            st["stream_following"] = False
            st["_stream_follow_primed"] = False
            return

        should_follow = st.get("stream_following", self._should_follow(text))
        if should_follow:
            primed = st.pop("_stream_follow_primed", False)
            if primed:
                st["stream_following"] = True
                return
            try:
                if hasattr(text, "yview_pickplace"):
                    text.yview_pickplace(mark)
                else:
                    text.see(mark)
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
        st["stream_active"] = False
        st["stream_following"] = False
        st["_stream_follow_primed"] = False
        self._cancel_stream_follow_job(st)
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

    def _caret_within_tag(self, content: str, cursor_offset: int) -> bool:
        try:
            tokens = list(parse_triple_tokens(content))
        except TagParseError:
            tokens = None

        if tokens is not None:
            return self._find_active_tag(tokens, cursor_offset) is not None

        for match in TRIPLE_RE.finditer(content):
            if cursor_within_span(match.start(), match.end(), cursor_offset):
                return True

        return False

    def _highlight_tag_span(
        self, st: dict, *, start: int, end: int, content: str | None = None
    ) -> None:
        text: tk.Text | None = st.get("text") if st else None
        if not text:
            return

        if content is None:
            content = text.get("1.0", tk.END)

        try:
            start_index = offset_to_tkindex(content, start)
            end_index = offset_to_tkindex(content, end)
        except Exception:
            return

        with contextlib.suppress(tk.TclError):
            text.tag_remove("sel", "1.0", tk.END)
            text.tag_add("sel", start_index, end_index)
            text.mark_set(tk.INSERT, start_index)
            text.see(start_index)
            text.focus_set()

    def _highlight_tag_at_cursor(
        self, st: dict, *, content: str, cursor_offset: int
    ) -> None:
        for match in TRIPLE_RE.finditer(content):
            if cursor_within_span(match.start(), match.end(), cursor_offset):
                self._highlight_tag_span(
                    st, start=match.start(), end=match.end(), content=content
                )
                break

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
        text.insert(cur, piece)
        st["stream_accumulated"] = st.get("stream_accumulated", "") + piece
        with contextlib.suppress(tk.TclError):
            text.tag_remove("misspelled", cur, f"{cur}+{len(piece)}c")
        self._maybe_follow_stream(st, mark)
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
        if self._is_log_tab(st):
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
            self._highlight_tag_at_cursor(st, content=content, cursor_offset=cursor_offset)
            self._show_unsupported_fim_error(exc)
            return

        guidance = (
            "Place the caret inside or immediately after a FIM tag "
            "to generate."
        )

        marker_token = self._find_active_tag(tokens, cursor_offset)
        if marker_token is None:
            self._show_message("Generate", guidance, parent=text_widget)
            return

        if marker_token.kind != "fim" or not isinstance(marker_token.tag, FIMTag):
            self._highlight_tag_span(
                st,
                start=marker_token.start,
                end=marker_token.end,
                content=content,
            )
            self._show_message("Generate", guidance, parent=text_widget)
            return

        try:
            fim_request = parse_fim_request(
                content,
                cursor_offset,
                tokens=tokens,
                marker_token=marker_token,
                force_completion=self._fim_tokens_missing(),
            )
        except TagParseError as exc:
            self._highlight_tag_span(
                st,
                start=marker_token.start,
                end=marker_token.end,
                content=content,
            )
            self._show_unsupported_fim_error(exc)
            return
        if fim_request is not None:
            self._launch_fim_or_completion_stream(st, content, fim_request)
            return

        self._show_message(
            "Generate",
            guidance,
            parent=text_widget,
        )

    def _interrupt_stream_for_tab(self, frame: tk.Misc | None) -> None:
        if frame is None:
            return

        st = self.tabs.get(frame)
        if not st:
            return

        stop_event = st.get("stream_stop_event")
        if stop_event is None:
            return

        st["stream_cancelled"] = True
        st["stream_patterns"] = []
        st["stream_accumulated"] = ""
        st["post_actions"] = []

        stop_event.set()

        tab_id = str(frame)
        self._result_queue.put({"ok": True, "kind": "stream_done", "tab": tab_id})

    def interrupt_stream(self):
        if not self._fim_generation_active:
            return

        tab_id = self.nb.select()
        if not tab_id:
            return

        frame = self.nametowidget(tab_id)
        self._interrupt_stream_for_tab(frame)

    def paste_last_fim_tag(self):
        st = self._current_tab_state()
        if not st:
            return
        if self._is_log_tab(st):
            return

        text_widget = st.get("text")
        if text_widget is None:
            return

        marker = self._last_fim_marker or "[[[20]]]"

        try:
            cursor_index = text_widget.index(tk.INSERT)
            cursor_offset = int(text_widget.count("1.0", cursor_index, "chars")[0])
        except Exception:
            cursor_offset = None

        content = text_widget.get("1.0", tk.END)
        if cursor_offset is None:
            cursor_offset = len(content)
        cursor_offset = max(0, min(len(content), cursor_offset))

        if self._caret_within_tag(content, cursor_offset):
            self._show_error(
                "Repeat Last FIM",
                "You cannot paste the last FIM tag when the caret is within a tag.",
            )
            return

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
        if self._is_log_tab(st):
            return

        text_widget = st.get("text")
        if text_widget is None:
            return

        marker = self._last_fim_marker or "[[[20]]]"

        try:
            cursor_index = text_widget.index(tk.INSERT)
            cursor_offset = int(text_widget.count("1.0", cursor_index, "chars")[0])
        except Exception:
            cursor_offset = None

        content = text_widget.get("1.0", tk.END)
        if cursor_offset is None:
            cursor_offset = len(content)
        cursor_offset = max(0, min(len(content), cursor_offset))

        if self._caret_within_tag(content, cursor_offset):
            self._show_error(
                "Repeat Last FIM",
                "You cannot repeat the last FIM tag when the caret is within a tag.",
            )
            return

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

    # ----- FIM/completion streaming -----

    def _launch_fim_or_completion_stream(self, st, content, fim_request: FIMRequest):
        cfg = self.cfg
        self._last_fim_marker = fim_request.marker.raw
        st["active_fim_request"] = fim_request

        request_cfg = {
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "max_tokens": fim_request.max_tokens,
        }
        request_cfg.update(fim_request.config_overrides)

        if fim_request.use_completion:
            # Completion fallback: ignore any suffix text when building the
            # prompt, but keep ``safe_suffix`` for logging/debugging.
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
        st["stream_active"] = True
        st["stream_following"] = self.cfg.get("follow_stream_enabled", True)

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
            for extra in fim_request.prepend_actions:
                with contextlib.suppress(tk.TclError):
                    text.insert("stream_here", extra)
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
            st["stream_active"] = False
            st.pop("active_fim_request", None)
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
                            st_err["stream_active"] = False
                            st_err.pop("active_fim_request", None)
                        self._fim_generation_active = False
                        self._set_busy(False)
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
                            if st:
                                st["stream_active"] = False
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

                                    removed_count = 0
                                    if (
                                        match.action == "chop"
                                        and len(target_text) < len(accumulated)
                                    ):
                                        removed_count = len(accumulated) - len(target_text)

                                        flush_mark = st.get("stream_mark") or mark or "stream_here"

                                        try:
                                            end_idx = text.index(flush_mark)
                                            start_idx = text.index(f"{end_idx}-{removed_count}c")
                                            text.delete(start_idx, end_idx)
                                        except tk.TclError:
                                            pass

                                        accumulated = target_text

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
                        generated_text = st.get("stream_accumulated", "")
                        st["stream_patterns"] = []
                        fim_request = st.pop("active_fim_request", None)
                        if fim_request:
                            self._log_fim_generation(fim_request, generated_text)
                        st["stream_accumulated"] = ""
                        st["stream_stop_event"] = None
                        for extra in st.get("post_actions", []):
                            try:
                                text.insert(mark, extra)
                                mark = text.index(f"{mark}+{len(extra)}c")
                            except tk.TclError:
                                continue
                            self._maybe_follow_stream(st, mark)
                        st["post_actions"] = []
                        self._end_stream_undo_group(st)
                        st["stream_active"] = False
                        self._fim_generation_active = False
                        self._set_busy(False)
                        self._set_dirty(st, True)

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
                    with contextlib.suppress(Exception):
                        self._end_stream_undo_group(st)
                    if st:
                        st["stream_active"] = False
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
                self._persist_config()
            return default_lang

        lang = preferred or default_lang
        if lang not in self._available_spell_langs:
            if default_lang in self._available_spell_langs:
                lang = default_lang
            else:
                lang = self._available_spell_langs[0]

        if self.cfg.get("spell_lang") != lang:
            self.cfg["spell_lang"] = lang
            self._persist_config()
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
            self._show_message("Spellcheck", self._spell_notice_msg)
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
        for frame, st in list(self.tabs.items()):
            if st.get("stream_stop_event") is not None:
                self._interrupt_stream_for_tab(frame)
        self._persist_config()
        self.destroy()


def main(
    argv: Sequence[str] | None = None,
    app_factory: Callable[[], FIMPad] = FIMPad,
) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    app = app_factory()
    if args:
        open_files = getattr(app, "open_files", None)
        if callable(open_files):
            open_files(args)
    app.mainloop()


if __name__ == "__main__":
    main()
