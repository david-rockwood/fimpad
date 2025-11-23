# fimpad/config.py
from __future__ import annotations

import json
import os
import re

APP_DIR = os.path.expanduser("~/.fimpad")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

SPELLCHECK_DEFAULT_LANG = "en_US"

DEFAULTS = {
    "endpoint": "http://localhost:8080",
    "temperature": 0.9,
    "top_p": 1.0,
    "fim_prefix": "<|fim_prefix|>",
    "fim_suffix": "<|fim_suffix|>",
    "fim_middle": "<|fim_middle|>",
    "font_family": "DejaVu Sans Mono",
    "font_size": 16,
    "editor_padding_px": 10,
    "line_number_padding_px": 10,
    "fg": "#141414",
    "bg": "#d8d8d8",
    "highlight1": "#b40a0a",
    "highlight2": "#a4a4a4",
    "open_maximized": False,
    "line_numbers_enabled": False,
    "spellcheck_enabled": True,
    "spell_lang": SPELLCHECK_DEFAULT_LANG,
}

WORD_RE = re.compile(r"\b[^\W\d_]+(?:['’][^\W\d_]+)*\b", re.UNICODE)


def load_config() -> dict:
    deprecated_keys = {"model", "default_n"}
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            save_config(DEFAULTS)
            return DEFAULTS.copy()
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        changed = False
        for k in list(data):
            if k in deprecated_keys:
                data.pop(k, None)
                changed = True
        for k, v in DEFAULTS.items():
            if k not in data:
                data[k] = v
                changed = True
        if changed:
            save_config(data)
        return data
    except Exception:
        return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
