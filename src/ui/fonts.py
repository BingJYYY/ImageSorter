"""Font loading helper. Registers the bundled Chinese font with Qt."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFontDatabase, QFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONT_FILE = ASSETS_DIR / "fonts" / "NotoSansCJKsc-Regular.otf"

_FAMILY = "AppCJK"


def current_family() -> str:
    return _FAMILY


def register_app_fonts() -> Optional[str]:
    """Register bundled font and return the family name to use."""
    if not FONT_FILE.exists():
        return None
    font_id = QFontDatabase.addApplicationFont(str(FONT_FILE))
    if font_id == -1:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        global _FAMILY
        _FAMILY = families[0]
        return _FAMILY
    return None


def app_font(size: int = 14, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Construct a QFont using the bundled CJK family."""
    f = QFont(_FAMILY, size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f
