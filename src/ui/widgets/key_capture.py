"""A control that captures a single key (with optional modifiers) from the user."""

from __future__ import annotations
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QPushButton

MOD_NAMES = {
    Qt.KeyboardModifier.ControlModifier: "Ctrl",
    Qt.KeyboardModifier.ShiftModifier: "Shift",
    Qt.KeyboardModifier.AltModifier: "Alt",
    Qt.KeyboardModifier.MetaModifier: "Win",
}


def keyevent_to_string(event: QKeyEvent) -> Optional[str]:
    """Convert a QKeyEvent to a canonical 'Ctrl+Shift+A' style string.

    Returns None if the event is only modifiers.
    """
    mods = event.modifiers()
    parts = []
    for flag, name in MOD_NAMES.items():
        if mods & flag:
            parts.append(name)
    key = event.key()
    if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
        return None
    name = QKeySequence(key).toString()
    if not name:
        # Some keys (arrows, function) map to "Left", "Right" etc.
        special = {
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Escape: "Escape",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "PageUp",
            Qt.Key.Key_PageDown: "PageDown",
            Qt.Key.Key_F1: "F1", Qt.Key.Key_F2: "F2", Qt.Key.Key_F3: "F3",
            Qt.Key.Key_F4: "F4", Qt.Key.Key_F5: "F5", Qt.Key.Key_F6: "F6",
            Qt.Key.Key_F7: "F7", Qt.Key.Key_F8: "F8", Qt.Key.Key_F9: "F9",
            Qt.Key.Key_F10: "F10", Qt.Key.Key_F11: "F11", Qt.Key.Key_F12: "F12",
        }
        name = special.get(key, "")
    if not name:
        return None
    parts.append(name)
    return "+".join(parts) if parts else name


class KeyCaptureButton(QPushButton):
    """Click to record a keybinding; click again or Esc to clear."""

    keyChanged = Signal(str)

    def __init__(self, initial: str = "", placeholder: str = "点击录制", parent=None):
        super().__init__(parent)
        self._value = initial or ""
        self._placeholder = placeholder
        self._recording = False
        self.setText(self._label())
        self.setMinimumWidth(120)
        self.clicked.connect(self._on_click)

    def value(self) -> str:
        return self._value

    def setValue(self, v: str) -> None:
        self._value = v or ""
        self.setText(self._label())

    def _label(self) -> str:
        if self._value:
            return self._value
        return self._placeholder

    def _on_click(self) -> None:
        self._recording = not self._recording
        if self._recording:
            self.setText("按下一个键…")
            self.setStyleSheet("background-color: #221F1C; border: 1px solid #D0A372;")
            self.grabKeyboard()
        else:
            self.setStyleSheet("")
            self.releaseKeyboard()
            self.setText(self._label())

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if not self._recording:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key.Key_Escape:
            self._recording = False
            self.releaseKeyboard()
            self.setStyleSheet("")
            self.setText(self._label())
            return
        # Backspace / Delete clears the binding.
        if e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._value = ""
            self.keyChanged.emit("")
            self._recording = False
            self.releaseKeyboard()
            self.setStyleSheet("")
            self.setText(self._label())
            return
        s = keyevent_to_string(e)
        if s is None:
            return
        self._value = s
        self.keyChanged.emit(s)
        self._recording = False
        self.releaseKeyboard()
        self.setStyleSheet("")
        self.setText(self._label())

    def clear(self) -> None:
        """Unbind the shortcut programmatically."""
        if self._recording:
            self._recording = False
            self.releaseKeyboard()
        if self._value:
            self._value = ""
            self.keyChanged.emit("")
        self.setStyleSheet("")
        self.setText(self._label())

    def mouseDoubleClickEvent(self, e) -> None:
        """Double-click to clear the binding."""
        if e.button() == Qt.MouseButton.LeftButton:
            self.clear()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)
