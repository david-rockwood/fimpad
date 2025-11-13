# fimpad/config.py
from __future__ import annotations

import json
import os
import re

APP_DIR = os.path.expanduser("~/.fimpad")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULTS = {
    "endpoint": "http://localhost:8080",
    "model": "granite-4.0-h-small-q6",
    "temperature": 0.9,
    "top_p": 1.0,
    "default_n": 100,
    "fim_prefix": "<|fim_prefix|>",
    "fim_suffix": "<|fim_suffix|>",
    "fim_middle": "<|fim_middle|>",
    "chat_system": "system",
    "chat_user": "user",
    "chat_assistant": "assistant",
    "font_family": "DejaVu Sans Mono",
    "font_size": 12,
    "editor_padding_px": 16,
    "fg": "#e6e6e6",
    "bg": "#1e1e1e",
    "spellcheck_enabled": True,
    "spell_lang": "en_US",
}

# Reuse your existing patterns
MARKER_REGEX = re.compile(
    r"""
    \[\[\[ \s* (?P<body> \d+ (?: \s*! \s* )? (?: \s+ (?: "(?:\\.|[^"\\])*" | '(?:\\.|[^'\\])*' ) )* ) \s* \]\]\]
    """,
    re.VERBOSE,
)
WORD_RE = re.compile(r"\b[^\W\d_]+(?:['’][^\W\d_]+)*\b", re.UNICODE)


def load_config() -> dict:
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        if not os.path.exists(CONFIG_PATH):
            save_config(DEFAULTS)
            return DEFAULTS.copy()
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    os.makedirs(APP_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
