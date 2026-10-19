"""Application icon loader.

Reads the PNG from ``E:/AI/AI应用图标/已处理/图片分类.png`` and produces a
``QIcon`` for the main window and PyInstaller EXE. Falls back to a built-in
blank icon when the file is missing so the app still launches.
"""
from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QGuiApplication


_ICON_PATH_CANDIDATES: tuple = (
    Path(__file__).resolve().parent.parent / "assets" / "icons" / "app.png",
    Path(r"E:/AI/AI应用图标/已处理/图片分类.png"),
    Path(r"E:/AI/AI应用图标/图片分类.png"),
)


def find_icon_path() -> Optional[Path]:
    for p in _ICON_PATH_CANDIDATES:
        if p and p.exists():
            return p
    return None


def load_app_icon() -> QIcon:
    """Return the app QIcon (loads the PNG and lets Qt scale it).

    QIcon auto-generates the OS-required 16/32/48/256 variants.
    """
    p = find_icon_path()
    icon = QIcon()
    if p is not None:
        pm = QPixmap(str(p))
        if not pm.isNull():
            icon.addPixmap(pm)
    if icon.isNull():
        # Render a fallback gold-on-black tile so the window still has an icon.
        pm = QPixmap(64, 64)
        pm.fill(QColor("#0C0A08"))
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#D0A372"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(8, 8, 48, 48, 10, 10)
        painter.setPen(QColor("#0C0A08"))
        f = painter.font()
        f.setBold(True)
        f.setPointSize(22)
        painter.setFont(f)
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        painter.end()
        icon.addPixmap(pm)
    return icon


def apply_app_icon(app: QGuiApplication) -> QIcon:
    """Set the application-wide icon (used in taskbar + window decoration)."""
    icon = load_app_icon()
    app.setWindowIcon(icon)
    return icon
