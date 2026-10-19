"""Match a QKeyEvent against a stored key string such as 'Ctrl+Z', 'P', 'Ctrl+Up'.

Stored format:
  - Modifiers may appear anywhere, separated by '+': Ctrl / Shift / Alt / Win / Meta
  - Exactly one main key, which is a single character (case-insensitive), or a
    special name like Left / Right / Up / Down / Space / Enter / Escape /
    Delete / Home / End / PageUp / PageDown / F1..F12 / 0..9.
"""

from __future__ import annotations
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence

MOD_NAMES = {
    "ctrl":   Qt.KeyboardModifier.ControlModifier,
    "shift":  Qt.KeyboardModifier.ShiftModifier,
    "alt":    Qt.KeyboardModifier.AltModifier,
    "meta":   Qt.KeyboardModifier.MetaModifier,
    "win":    Qt.KeyboardModifier.MetaModifier,
}

_LETTER_KEYS = {c: getattr(Qt.Key, f"Key_{c}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_DIGIT_KEYS = {d: getattr(Qt.Key, f"Key_{d}") for d in "0123456789"}


def _name_to_key(name: str):
    if not name:
        return None
    low = name.lower()
    specials = {
        "left": Qt.Key.Key_Left,
        "right": Qt.Key.Key_Right,
        "up": Qt.Key.Key_Up,
        "down": Qt.Key.Key_Down,
        "space": Qt.Key.Key_Space,
        "spacebar": Qt.Key.Key_Space,
        "enter": Qt.Key.Key_Return,
        "return": Qt.Key.Key_Return,
        "escape": Qt.Key.Key_Escape,
        "esc": Qt.Key.Key_Escape,
        "delete": Qt.Key.Key_Delete,
        "del": Qt.Key.Key_Delete,
        "home": Qt.Key.Key_Home,
        "end": Qt.Key.Key_End,
        "pageup": Qt.Key.Key_PageUp,
        "pgup": Qt.Key.Key_PageUp,
        "pagedown": Qt.Key.Key_PageDown,
        "pgdown": Qt.Key.Key_PageDown,
    }
    for i in range(1, 13):
        specials[f"f{i}"] = getattr(Qt.Key, f"Key_F{i}")
    if low in specials:
        return specials[low]
    if len(name) == 1:
        up = name.upper()
        if up in _LETTER_KEYS:
            return _LETTER_KEYS[up]
        if name in _DIGIT_KEYS:
            return _DIGIT_KEYS[name]
    return None


def parse_key_string(s: str) -> Optional[Tuple[int, Qt.KeyboardModifier]]:
    """Return (Qt.Key, required modifier mask) or None if invalid/empty."""
    if not s or not s.strip():
        return None
    parts: List[str] = [p.strip() for p in s.split("+") if p.strip()]
    if not parts:
        return None
    mods = Qt.KeyboardModifier.NoModifier
    main_name: Optional[str] = None
    for p in parts:
        pl = p.lower()
        if pl in MOD_NAMES:
            mods |= MOD_NAMES[pl]
        else:
            if main_name is not None:
                return None  # more than one main key
            main_name = p
    if main_name is None:
        return None
    key = _name_to_key(main_name)
    if key is None:
        return None
    return (key, mods)


def event_matches(event: QKeyEvent, key_string: str) -> bool:
    """True if event matches the stored key string. Empty string never matches."""
    parsed = parse_key_string(key_string)
    if parsed is None:
        return False
    want_key, want_mods = parsed
    if event.key() != want_key:
        return False
    actual = event.modifiers()
    # Required modifiers must be present; extra modifiers are tolerated only
    # when the stored string explicitly mentions them.
    return (actual & want_mods) == want_mods
