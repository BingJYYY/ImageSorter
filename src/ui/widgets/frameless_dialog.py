"""Frameless dialog with a hand-drawn title bar and native resize borders."""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import colors as C
from .button_style import apply_icon_button
from .win_hit_test import enable_native_resize_border, native_hit_test


class _DialogTitleBar(QWidget):
    closeRequested = Signal()

    HEIGHT = 40

    def __init__(self, dialog: QDialog, title: str):
        super().__init__(dialog)
        self._dialog = dialog
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("DialogTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)
        label = QLabel(title, self)
        label.setStyleSheet(
            f"color: {C.TEXT_PRIMARY}; background: transparent;"
            "font-weight: 600; font-size: 13px;"
        )
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(label, 1)
        close_btn = QPushButton("\u2715", self)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.closeRequested.emit)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent;"
            f" color: {C.TEXT_SECONDARY}; border: 0; padding: 0px; }}"
            "QPushButton:hover {"
            f" background: {C.ACCENT_RUST}; color: {C.TEXT_PRIMARY}; }}"
        )
        close_btn.setFixedSize(34, 28)
        layout.addWidget(close_btn)

        self.setStyleSheet(
            f"#DialogTitleBar {{ background-color: {C.BG_PANEL};"
            f" border-bottom: 1px solid {C.DIVIDER}; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint()
                - self._dialog.pos()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self._dialog.move(
                event.globalPosition().toPoint() - self._drag_pos
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # Dialogs do not maximise by convention; ignore double click.
        event.accept()


class FramelessDialog(QDialog):
    """Base dialog: custom title bar, drag, and native edge resizing."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setWindowTitle(title)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.title_bar = _DialogTitleBar(self, title)
        self.title_bar.closeRequested.connect(self.reject)
        outer.addWidget(self.title_bar)

        self._body = QWidget(self)
        self._body.setObjectName("FramelessDialogBody")
        self._body.setStyleSheet(
            f"#FramelessDialogBody {{ background-color: {C.BG_BASE}; }}"
        )
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        outer.addWidget(self._body, 1)

        self._native_border_enabled = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._native_border_enabled:
            self._native_border_enabled = True
            enable_native_resize_border(self)
            QTimer.singleShot(0, lambda: enable_native_resize_border(self))

    def nativeEvent(self, event_type, message):
        result = native_hit_test(self, event_type, message)
        if result is not None:
            return result
        return super().nativeEvent(event_type, message)
