"""Inline button styling helpers.

Qt's dynamic-property selectors (``QPushButton[accent="gold"]``) can be
unreliable when a widget is re-parented or polished more than once.  Every
critical action button therefore gets an explicit stylesheet so its label can
never end up dark-on-dark.
"""
from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from .. import colors as C


def apply_gold_button(btn: QPushButton, compact: bool = False) -> None:
    padding = "5px 14px" if compact else "8px 20px"
    radius = "10px" if compact else "12px"
    btn.setProperty("accent", "gold")
    btn.setStyleSheet(
        "QPushButton {"
        f" background-color: {C.ACCENT_GOLD};"
        f" color: {C.TEXT_INVERT};"
        f" border: 1px solid {C.ACCENT_GOLD};"
        f" border-radius: {radius};"
        f" padding: {padding};"
        " font-weight: 600;"
        "}"
        "QPushButton:hover { background-color: #E0B58A; border-color: #E0B58A; }"
        "QPushButton:pressed { background-color: #C99870; border-color: #C99870; }"
        "QPushButton:disabled {"
        f" background-color: {C.BG_PANEL_PRESSED};"
        f" color: {C.TEXT_DISABLED};"
        f" border-color: {C.BORDER};"
        "}"
    )


def apply_icon_button(btn: QPushButton, size: int = 28) -> None:
    btn.setProperty("accent", "icon")
    btn.setFixedSize(size, size)
    btn.setStyleSheet(
        "QPushButton {"
        f" background-color: transparent;"
        f" color: {C.TEXT_SECONDARY};"
        f" border: 1px solid {C.BORDER};"
        f" border-radius: {size // 2}px;"
        " padding: 0px;"
        "}"
        "QPushButton:hover {"
        f" background-color: {C.BG_PANEL_HOVER};"
        f" color: {C.TEXT_PRIMARY};"
        f" border-color: {C.DIVIDER_STRONG};"
        "}"
        "QPushButton:pressed {"
        f" background-color: {C.BG_PANEL_PRESSED};"
        "}"
    )
