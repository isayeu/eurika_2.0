"""Unified UI styles for Eurika Qt shell (polish, consistency)."""

from __future__ import annotations

# Spacing (theme-independent)
CONTENT_MARGINS = (10, 10, 10, 10)
TAB_MARGINS = (8, 8, 8, 8)
SECTION_SPACING = 8

# Compact controls
COMBO_MAX_WIDTH = 220
SPIN_MAX_WIDTH = 80
INPUT_MAX_WIDTH = 200
BTN_COMPACT_WIDTH = 120
BTN_SMALL_WIDTH = 110

# Light theme
_LIGHT = {
    "hint_bg": "#f5f0e6",
    "hint_border": "#ddd",
    "hint_text": "#444",
    "secondary": "#666",
    "status": "#666",
}

# Dark theme
_DARK = {
    "hint_bg": "#2d2d2d",
    "hint_border": "#404040",
    "hint_text": "#b0b0b0",
    "secondary": "#909090",
    "status": "#909090",
}

_current_dark = False


def set_theme_dark(dark: bool) -> None:
    """Set current theme. Affects get_hint_stylesheet, get_secondary_hint, get_status_style."""
    global _current_dark
    _current_dark = bool(dark)


def is_dark_theme() -> bool:
    return _current_dark


def _colors() -> dict:
    return _DARK if _current_dark else _LIGHT


def get_hint_stylesheet() -> str:
    c = _colors()
    return f"""
QFrame {{
    background-color: {c['hint_bg']};
    border: 1px solid {c['hint_border']};
    border-radius: 6px;
}}
"""


def get_hint_label_stylesheet() -> str:
    c = _colors()
    return f"color: {c['hint_text']}; font-size: 13px;"


def get_secondary_hint() -> str:
    c = _colors()
    return f"color: {c['secondary']}; font-size: 11px;"


def get_status_style() -> str:
    c = _colors()
    return f"color: {c['status']}; padding: 4px 0;"
