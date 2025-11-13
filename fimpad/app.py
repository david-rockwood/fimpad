#!/usr/bin/env python3
"""
FIMpad — Tabbed Tkinter editor for llama-server
with FIM + Chat, streaming, dirty tracking, and aspell spellcheck.
"""

import contextlib
import os
import queue
import re
import subprocess
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .client import stream_chat, stream_completion
from .config import DEFAULTS, MARKER_REGEX, WORD_RE, load_config, save_config
from .help import get_help_template
from .utils import offset_to_tkindex

PREFIX_TAG_RE = re.compile(r"\[\[\[\s*prefix\s*\]\]\]", re.IGNORECASE)
SUFFIX_TAG_RE = re.compile(r"\[\[\[\s*suffix\s*\]\]\]", re.IGNORECASE)


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

        self._build_menu()
        self._build_notebook()
        self.nb.bind(
            "<<NotebookTabChanged>>",
            lambda e: self._schedule_spellcheck_for_frame(self.nb.select(), delay_ms=80),
        )

        self._result_queue = queue.Queue()
        self.after(60, self._poll_queue)

        self._aspell_available = self._probe_aspell()
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
        self.bind_all("<Control-a>", lambda e: self._select_all_current())  # select all
        self.bind_all("<Control-t>", lambda e: self._open_settings())

        def _help_binding(event=None):
            self._open_help_tab()
            return "break"

        self.bind_all("<Alt-h>", _help_binding)
        self.bind_all("<Alt-H>", _help_binding)

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
            "stops_after": [],
            "stops_after_maxlen": 0,
            "stream_tail": "",
            "stream_cancelled": False,
            "chat_after_placeholder_mark": None,
            "chat_stream_active": False,
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
        self.nb.select(frame)

        # Initial spellcheck (debounced)
        self._schedule_spellcheck_for_frame(frame, delay_ms=250)

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
        self.nb.tab(tab, text=title)

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
        editmenu.add_command(
            label="Toggle Wrap", accelerator="Alt+Z", command=self._toggle_wrap_current
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
        aimenu.add_command(
            label="Help",
            accelerator="Alt+H",
            command=self._open_help_tab,
        )
        menubar.add_cascade(label="AI", menu=aimenu)

        self.config(menu=menubar)

    def _open_help_tab(self):
        title = "AI Help"
        template = get_help_template()

        for tab_id in self.nb.tabs():
            if self.nb.tab(tab_id, "text") == title:
                self.nb.select(tab_id)
                frame = self.nametowidget(tab_id)
                st = self.tabs.get(frame)
                if st:
                    self._focus_help_blank_line(st["text"], template)
                return

        self._new_tab(content=template, title=title)
        st = self._current_tab_state()
        if not st:
            return
        self._focus_help_blank_line(st["text"], template)

    def _focus_help_blank_line(self, text_widget: ScrolledText, template: str) -> None:
        user_open = "[[[user]]]"
        user_close = "[[[/user]]]"
        start = template.find(user_open)
        end = template.find(user_close, start + len(user_open) if start != -1 else 0)
        if start == -1 or end == -1:
            insert_offset = 0
        else:
            region = template[start + len(user_open) : end]
            rel = region.find("\n\n")
            if rel == -1:
                insert_offset = start + len(user_open)
            else:
                insert_offset = start + len(user_open) + rel + 1

        index = offset_to_tkindex(template, insert_offset)
        text_widget.mark_set(tk.INSERT, index)
        text_widget.tag_remove("sel", "1.0", tk.END)
        text_widget.see(tk.INSERT)
        text_widget.focus_set()

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
        text = st["text"]
        if st["wrap"] == "word":
            st["wrap"] = "none"
            text.config(wrap=tk.NONE)
        else:
            st["wrap"] = "word"
            text.config(wrap=tk.WORD)
        self._apply_editor_padding(text, self.cfg["editor_padding_px"])

    def _select_all_current(self):
        st = self._current_tab_state()
        if not st:
            return
        t = st["text"]
        t.tag_add("sel", "1.0", "end-1c")
        t.mark_set(tk.INSERT, "1.0")
        t.see("1.0")

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

        chat_sys_var = tk.StringVar(value=cfg["chat_system"])
        chat_usr_var = tk.StringVar(value=cfg["chat_user"])
        chat_ast_var = tk.StringVar(value=cfg["chat_assistant"])

        fontfam_var = tk.StringVar(value=cfg["font_family"])
        fontsize_var = tk.StringVar(value=str(cfg["font_size"]))
        pad_var = tk.StringVar(
            value=str(cfg.get("editor_padding_px", DEFAULTS["editor_padding_px"]))
        )
        fg_var = tk.StringVar(value=cfg["fg"])
        bg_var = tk.StringVar(value=cfg["bg"])

        spell_on_var = tk.BooleanVar(value=cfg.get("spellcheck_enabled", True))
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

        tk.Label(
            w, text="Chat Roles (inside triple brackets)", font=("TkDefaultFont", 10, "bold")
        ).grid(row=row, column=0, padx=8, pady=(10, 4), sticky="w")
        row += 1
        add_row(row, "[[[system]]]: role name", chat_sys_var)
        row += 1
        add_row(row, "[[[user]]]: role name", chat_usr_var)
        row += 1
        add_row(row, "[[[assistant]]]: role name", chat_ast_var)
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

        # Spellcheck controls
        ttk.Checkbutton(w, text="Enable spellcheck (aspell)", variable=spell_on_var).grid(
            row=row, column=0, columnspan=2, padx=8, pady=(10, 0), sticky="w"
        )
        row += 1
        tk.Label(w, text="Spellcheck language (aspell):").grid(
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
                self.cfg["chat_system"] = chat_sys_var.get().strip()
                self.cfg["chat_user"] = chat_usr_var.get().strip()
                self.cfg["chat_assistant"] = chat_ast_var.get().strip()
                self.cfg["font_family"] = fontfam_var.get().strip() or DEFAULTS["font_family"]
                self.cfg["font_size"] = max(6, min(72, int(fontsize_var.get())))
                self.cfg["editor_padding_px"] = max(0, int(pad_var.get()))
                self.cfg["fg"] = fg_var.get().strip()
                self.cfg["bg"] = bg_var.get().strip()
                self.cfg["spellcheck_enabled"] = bool(spell_on_var.get())
                self.cfg["spell_lang"] = spell_lang_var.get().strip() or "en_US"
            except Exception as e:
                messagebox.showerror("Settings", f"Invalid value: {e}")
                return
            save_config(self.cfg)
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

    def _clear_chat_state(self, st):
        text = st.get("text")
        mark_name = st.get("chat_after_placeholder_mark")
        if text is not None and mark_name:
            with contextlib.suppress(tk.TclError):
                text.mark_unset(mark_name)
        st["chat_after_placeholder_mark"] = None
        st["chat_stream_active"] = False

    def _reset_stream_state(self, st):
        job = st.get("stream_flush_job")
        if job is not None:
            with contextlib.suppress(Exception):
                self.after_cancel(job)
        st["stream_flush_job"] = None
        st["stream_buffer"].clear()
        st["stream_mark"] = None
        st["stops_after"] = []
        st["stops_after_maxlen"] = 0
        st["stream_tail"] = ""
        st["stream_cancelled"] = False
        self._clear_chat_state(st)

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
        should_follow = self._should_follow(text)
        text.insert(cur, piece)
        text.mark_set(mark, f"{cur}+{len(piece)}c")
        if should_follow:
            text.see(mark)
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

        match_for_cursor = None
        for marker_match in MARKER_REGEX.finditer(content):
            if not self._cursor_within_span(
                marker_match.start(), marker_match.end(), cursor_offset
            ):
                continue
            if match_for_cursor is None or marker_match.start() >= match_for_cursor.start():
                match_for_cursor = marker_match

        if match_for_cursor is not None:
            self._launch_fim_or_completion_stream(
                st,
                content,
                match_for_cursor.start(),
                match_for_cursor.end(),
                match_for_cursor,
            )
            return

        chat_bounds = self._locate_chat_block(content, cursor_offset)
        if chat_bounds:
            self._reset_stream_state(st)
            messages = self._prepare_chat_block(st, content, chat_bounds[0], chat_bounds[1])
            if not messages:
                messagebox.showinfo("Chat", "No parsed chat messages in this block.")
                return

            self._launch_chat_stream(st, messages)
            return

        if self._contains_chat_tags(content):
            messagebox.showinfo("Chat", "Place the cursor inside a chat block.")
            return

        messagebox.showinfo(
            "Generate",
            "Place the caret inside a [[[N]]] marker or chat tag block.",
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

    def _launch_fim_or_completion_stream(self, st, content, mstart, mend, marker_match):
        cfg = self.cfg
        self._last_fim_marker = marker_match.group(0)
        body = (marker_match.group("body") or "").strip()

        remainder = body
        token_value: int | str | None = None
        keep_tags = False
        if remainder:
            n_match = re.match(r"(\d+)", remainder)
            if n_match:
                token_value = n_match.group(1)
                remainder = remainder[n_match.end() :]
                bang_match = re.match(r"\s*!\s*", remainder)
                if bang_match:
                    keep_tags = True
                    remainder = remainder[bang_match.end() :]
                remainder = remainder.strip()
            else:
                remainder = remainder.strip()
        else:
            remainder = ""

        if token_value is None:
            token_value = cfg["default_n"]

        try:
            max_tokens = max(1, min(4096, int(token_value)))
        except Exception:
            max_tokens = cfg["default_n"]

        def _unescape_stop(s: str) -> str:
            out: list[str] = []
            i = 0
            while i < len(s):
                c = s[i]
                if c != "\\":
                    out.append(c)
                    i += 1
                    continue
                i += 1
                if i >= len(s):
                    out.append("\\")
                    break
                esc = s[i]
                i += 1
                if esc == "n":
                    out.append("\n")
                elif esc == "t":
                    out.append("\t")
                elif esc == "r":
                    out.append("\r")
                elif esc == '"':
                    out.append('"')
                elif esc == "'":
                    out.append("'")
                elif esc == "\\":
                    out.append("\\")
                else:
                    out.append(esc)
            return "".join(out)

        stops_before: list[str] = []
        stops_after: list[str] = []
        quote_re = re.compile(r"\"((?:\\.|[^\"\\])*)\"|'((?:\\.|[^'\\])*)'")
        for qmatch in quote_re.finditer(remainder):
            double_val = qmatch.group(1)
            single_val = qmatch.group(2)
            if double_val is not None:
                unescaped = _unescape_stop(double_val)
                if unescaped:
                    stops_before.append(unescaped)
            elif single_val is not None:
                unescaped = _unescape_stop(single_val)
                if unescaped:
                    stops_after.append(unescaped)

        pfx_match = None
        for m in PREFIX_TAG_RE.finditer(content, 0, mstart):
            pfx_match = m

        if pfx_match is not None:
            pfx_used_start = pfx_match.start()
            pfx_used_end = pfx_match.end()
            before_region = content[pfx_used_end:mstart]
        else:
            before_region = content[:mstart]

        sfx_match = SUFFIX_TAG_RE.search(content, mend)
        if sfx_match is not None:
            sfx_used_start = sfx_match.start()
            sfx_used_end = sfx_match.end()
            after_region = content[mend:sfx_used_start]
        else:
            after_region = content[mend:]

        safe_suffix = MARKER_REGEX.sub("", after_region)
        use_completion = after_region.strip() == ""

        if use_completion:
            prompt = before_region
        else:
            prompt = (
                f"{cfg['fim_prefix']}{before_region}{cfg['fim_suffix']}{safe_suffix}{cfg['fim_middle']}"
            )

        payload = {
            "model": cfg["model"],
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "stream": True,
        }
        if stops_before:
            payload["stop"] = stops_before

        text = st["text"]
        start_index = offset_to_tkindex(content, mstart)
        end_index = offset_to_tkindex(content, mend)

        self._reset_stream_state(st)

        st["stops_after"] = stops_after
        st["stops_after_maxlen"] = max((len(s) for s in stops_after), default=0)
        st["stream_tail"] = ""
        st["stream_cancelled"] = False

        self._set_busy(True)

        # Prepare streaming mark
        text.mark_set("stream_here", start_index)
        text.mark_gravity("stream_here", tk.RIGHT)
        if sfx_match is not None and not keep_tags:
            s_s = offset_to_tkindex(content, sfx_used_start)
            s_e = offset_to_tkindex(content, sfx_used_end)
            with contextlib.suppress(tk.TclError):
                text.delete(s_s, s_e)
        if pfx_match is not None and not keep_tags:
            p_s = offset_to_tkindex(content, pfx_used_start)
            p_e = offset_to_tkindex(content, pfx_used_end)
            with contextlib.suppress(tk.TclError):
                text.delete(p_s, p_e)

        marker_len = mend - mstart
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

    # ----- Chat streaming -----

    def _chat_role_aliases(self) -> dict[str, str]:
        cfg = self.cfg
        base_aliases = {
            cfg["chat_system"].lower(): "system",
            cfg["chat_user"].lower(): "user",
            cfg["chat_assistant"].lower(): "assistant",
            "system": "system",
            "user": "user",
            "assistant": "assistant",
            "s": "system",
            "u": "user",
            "a": "assistant",
        }

        aliases = {}
        for name, role in base_aliases.items():
            aliases[name] = role
            if not name.startswith("/"):
                aliases[f"/{name}"] = role

        return aliases

    def _chat_tag_names(self) -> list[str]:
        role_aliases = self._chat_role_aliases()
        tag_names = {name.lstrip("/") for name in role_aliases}
        return sorted(tag_names, key=len, reverse=True)

    def _contains_chat_tags(self, content: str) -> bool:
        tag_names = self._chat_tag_names()
        pat = re.compile(
            rf"\[\[\[\s*/?\s*(?:{'|'.join(re.escape(name) for name in tag_names)})\s*\]\]\]",
            re.IGNORECASE,
        )
        return bool(pat.search(content))

    @staticmethod
    def _cursor_within_span(start: int, end: int, cursor_offset: int) -> bool:
        return (start <= cursor_offset <= end) or (
            cursor_offset > 0 and start <= cursor_offset - 1 < end
        )

    def _locate_chat_block(self, content: str, cursor_offset: int):
        cursor_offset = max(0, min(len(content), cursor_offset))
        role_aliases = self._chat_role_aliases()
        system_names = sorted(
            {name.lstrip("/") for name, role in role_aliases.items() if role == "system"},
            key=len,
            reverse=True,
        )
        sys_re = re.compile(
            rf"\[\[\[\s*(?:{'|'.join(re.escape(name) for name in system_names)})\s*\]\]\]",
            re.IGNORECASE,
        )
        matches = list(sys_re.finditer(content))
        if not matches:
            return None

        for idx in range(len(matches) - 1, -1, -1):
            start = matches[idx].start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            if self._cursor_within_span(start, end, cursor_offset):
                return start, end

        return None

    def _parse_chat_messages(self, content: str):
        role_aliases = self._chat_role_aliases()
        tag_names = self._chat_tag_names()
        tag_re = re.compile(
            rf"(\[\[\[\s*(/)?\s*({'|'.join(re.escape(name) for name in tag_names)})\s*\]\]\])",
            re.IGNORECASE,
        )
        tokens = []
        last_end = 0
        for m in tag_re.finditer(content):
            if m.start() > last_end:
                tokens.append(("TEXT", content[last_end : m.start()]))
            tokens.append(("TAG", m.group(0), m.group(2) is not None, m.group(3)))
            last_end = m.end()
        if last_end < len(content):
            tokens.append(("TEXT", content[last_end:]))

        messages = []
        cur_role = None
        buf = []

        def flush():
            nonlocal cur_role, buf
            if cur_role is not None:
                messages.append({"role": cur_role.lower(), "content": "".join(buf)})
                cur_role = None
                buf = []

        for t in tokens:
            if t[0] == "TEXT":
                if cur_role is not None:
                    buf.append(t[1])
            else:
                _, _raw, is_close, role = t
                role_key = role.lower()
                role = role_aliases.get(role_key, role_aliases.get(f"/{role_key}", role_key))
                if not is_close:
                    flush()
                    cur_role = role
                    buf = []
                else:
                    if cur_role == role:
                        flush()
                    else:
                        flush()
                        cur_role = None
                        buf = []
        flush()
        return messages

    def _prepare_chat_block(self, st, full_content: str, block_start: int, block_end: int):
        block_text = full_content[block_start:block_end]
        parsed = self._parse_chat_messages(block_text)
        if not parsed:
            return []

        cfg = self.cfg
        text = st["text"]

        role_lookup = {
            cfg["chat_system"].lower(): cfg["chat_system"],
            cfg["chat_user"].lower(): cfg["chat_user"],
            cfg["chat_assistant"].lower(): cfg["chat_assistant"],
        }
        role_lookup.setdefault("system", cfg["chat_system"])
        role_lookup.setdefault("user", cfg["chat_user"])
        role_lookup.setdefault("assistant", cfg["chat_assistant"])

        normalized_messages = []
        pieces: list[str] = []
        for msg in parsed:
            role = (msg.get("role") or "").lower()
            body = (msg.get("content") or "").rstrip("\n")
            if body.startswith("\n"):
                body = body[1:]
            normalized_messages.append({"role": role, "content": body})

            tag_name = role_lookup.get(role, role)
            open_tag = f"[[[{tag_name}]]]"
            close_tag = f"[[[/{tag_name}]]]"

            pieces.append(open_tag)
            pieces.append("\n")
            if body:
                pieces.append(body)
                pieces.append("\n")
            pieces.append(close_tag)
            pieces.append("\n\n")

        normalized_text = "".join(pieces)

        assistant_tag = cfg["chat_assistant"]
        placeholder_open = f"[[[{assistant_tag}]]]"
        placeholder_close = f"[[[/{assistant_tag}]]]"
        placeholder = f"{placeholder_open}\n\n{placeholder_close}"

        replacement = normalized_text + placeholder

        start_idx = offset_to_tkindex(full_content, block_start)
        end_idx = offset_to_tkindex(full_content, block_end)

        text.delete(start_idx, end_idx)
        text.insert(start_idx, replacement)

        normalized_len = len(normalized_text)
        open_len = len(placeholder_open)
        close_len = len(placeholder_close)

        stream_offset = normalized_len + open_len + 1
        after_close_offset = normalized_len + open_len + 2 + close_len

        stream_index = text.index(f"{start_idx}+{stream_offset}c")
        text.mark_set("stream_here", stream_index)
        text.mark_gravity("stream_here", tk.RIGHT)

        after_close_index = text.index(f"{start_idx}+{after_close_offset}c")
        text.mark_set("chat_after_placeholder", after_close_index)
        text.mark_gravity("chat_after_placeholder", tk.RIGHT)
        st["chat_after_placeholder_mark"] = "chat_after_placeholder"

        normalized_messages.append({"role": "assistant", "content": ""})

        return normalized_messages

    def _launch_chat_stream(self, st, messages):
        cfg = self.cfg
        text = st["text"]

        assistant_role = cfg["chat_assistant"].lower()
        payload_messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if not (
                msg["role"].lower() == assistant_role and not (msg["content"] or "").strip()
            )
        ]

        if not payload_messages:
            messagebox.showinfo("Chat", "No parsed chat messages in this block.")
            self._clear_chat_state(st)
            return

        payload = {
            "model": cfg["model"],
            "messages": payload_messages,
            "temperature": cfg["temperature"],
            "top_p": cfg["top_p"],
            "stream": True,
        }

        self._set_busy(True)

        st["stream_mark"] = "stream_here"
        st["chat_stream_active"] = True

        if self._should_follow(text):
            text.see("stream_here")

        def worker(tab_id):
            try:
                for piece in stream_chat(cfg["endpoint"], payload):
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
                        self._clear_chat_state(st_err)
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
                    if st.get("chat_stream_active"):
                        after_idx = None
                        mark_name = st.get("chat_after_placeholder_mark")
                        if mark_name:
                            try:
                                after_idx = text.index(mark_name)
                            except tk.TclError:
                                after_idx = None
                        if after_idx:
                            urole = self.cfg["chat_user"]
                            open_tag = f"[[[{urole}]]]"
                            user_block = f"\n\n{open_tag}\n\n[[[/{urole}]]]"
                            text.insert(after_idx, user_block)
                            cursor_offset = len("\n\n" + open_tag + "\n")
                            insert_target = text.index(f"{after_idx}+{cursor_offset}c")
                            text.mark_set(tk.INSERT, insert_target)
                            text.see(tk.INSERT)
                        self._clear_chat_state(st)
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

    # ---------- Spellcheck (aspell) ----------

    def _probe_aspell(self) -> bool:
        try:
            subprocess.run(
                ["aspell", "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return True
        except Exception:
            return False

    def _schedule_spellcheck_for_frame(self, frame, delay_ms: int = 350):
        """
        Schedule a debounced spellcheck for the given tab/frame.
        Accepts either a ttk.Frame object or a Notebook tab-id string.
        """
        # Respect settings / availability
        if not self.cfg.get("spellcheck_enabled", True) or not self._aspell_available:
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
        if frame not in self.tabs:
            return
        st = self.tabs[frame]
        t = st["text"]
        # Snapshot text (must be on main thread)
        txt = t.get("1.0", "end-1c")
        lang = self.cfg.get("spell_lang", "en_US")
        ignore = set(self._spell_ignore)  # copy

        def worker(tab_id, text_snapshot, lang_code, ignore_set):
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

                # Ask aspell which are misspelled
                p = subprocess.run(
                    ["aspell", "--lang", lang_code, "list"],
                    input=("\n".join(words)).encode("utf-8"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                miss = set(w.strip() for w in p.stdout.decode("utf-8").splitlines() if w.strip())

                # Filter ignores
                miss = {w for w in miss if w not in ignore_set}

                if not miss:
                    self._result_queue.put(
                        {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                    )
                    return

                # Map misspelled words back to spans
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
            except Exception:
                # swallow spell errors silently
                self._result_queue.put(
                    {"ok": True, "kind": "spell_result", "tab": tab_id, "spans": []}
                )

        threading.Thread(
            target=worker, args=(self.nb.select(), txt, lang, ignore), daemon=True
        ).start()

    def _spell_context_menu(self, event, frame):
        if not self.cfg.get("spellcheck_enabled", True) or not self._aspell_available:
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

        suggs = self._aspell_suggestions(word)
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

    def _aspell_suggestions(self, word):
        if not self._aspell_available:
            return []
        try:
            lang = self.cfg.get("spell_lang", "en_US")
            p = subprocess.run(
                ["aspell", "--lang", lang, "-a"],
                input=(word + "\n").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            lines = p.stdout.decode("utf-8", errors="ignore").splitlines()
            for line in lines[1:]:  # skip header
                if not line:
                    continue
                ch = line[0]
                if ch in ("*", "+"):  # correct or already root
                    return []
                if ch in ("&", "#"):
                    parts = line.split(":")
                    if len(parts) > 1:
                        return [s.strip() for s in parts[1].split(",")]
            return []
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
