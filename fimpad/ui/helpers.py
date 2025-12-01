import contextlib
import tkinter as tk


def apply_editor_padding(st: dict, pad_px: int, bg: str) -> None:
    pad_px = max(0, int(pad_px))
    st["text"].configure(padx=0, pady=0)
    for key in ("left_padding", "right_padding"):
        pad = st.get(key)
        if pad is not None:
            pad.configure(width=pad_px, bg=bg, highlightthickness=0, bd=0)


def apply_line_number_padding(st: dict, pad_px: int, bg: str) -> None:
    pad_px = max(0, int(pad_px))
    gap = st.get("gutter_gap")
    if gap is not None:
        gap.configure(width=pad_px, bg=bg, highlightthickness=0, bd=0)


def reflow_text_layout(text: tk.Text) -> None:
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


def clear_line_spacing(text: tk.Text) -> None:
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
