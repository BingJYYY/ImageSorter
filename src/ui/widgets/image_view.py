"""Zoomable/pannable image viewer widget."""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QSize
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QWheelEvent, QKeyEvent,
    QMouseEvent, QTransform, QPaintEvent, QResizeEvent,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

from ...core.image_loader import open_for_display, load_raw_library


class ImageView(QWidget):
    """Display a single image with fit-to-window and free zoom."""

    rawLoadingRequested = Signal()
    rawLoadFinished = Signal(bool)
    wheelSwitchRequested = Signal(int)  # -1 prev, +1 next

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pixmap: Optional[QPixmap] = None
        self._path: Optional[Path] = None
        self._zoom: float = 1.0
        self._fit_zoom: float = 1.0
        self._offset: QPointF = QPointF(0, 0)
        self._dragging = False
        self._last_pos = QPointF()
        self.setStyleSheet("background-color: #0C0A08;")

    # ----- public API -----
    def show_path(self, path: Path) -> None:
        self._path = Path(path)
        self._pixmap = None
        self._zoom = -1.0
        try:
            if self._path.suffix.lower() in {".cr2", ".cr3", ".nef", ".arw", ".dng",
                                            ".raf", ".orf", ".rw2", ".pef", ".srw", ".x3f"}:
                from ...core.image_loader import RAW_LIB_LOADED
                if not RAW_LIB_LOADED:
                    self.rawLoadingRequested.emit()
                    load_raw_library(on_loaded=lambda: self.rawLoadFinished.emit(True),
                                     on_error=lambda e: self.rawLoadFinished.emit(False))
                    self._placeholder("正在加载 RAW 解码库…")
                    return
            img = open_for_display(self._path)
            img = img.convert("RGB") if img.mode != "RGB" else img
            data = img.tobytes("raw", "RGB")
            w, h = img.size
            qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self._pixmap = QPixmap.fromImage(qimg)
            img.close()
            self._zoom = -1.0
            self._apply_fit()
        except Exception as e:
            self._placeholder(f"无法打开图片\n{e}")
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._path = None
        self.update()

    def zoom_factor(self) -> float:
        return self._zoom if self._zoom > 0 else self._fit_zoom

    def set_zoom(self, factor: float) -> None:
        if self._pixmap is None:
            return
        self._zoom = max(0.05, min(20.0, factor))
        self._clamp_offset()
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self.zoom_factor() * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.zoom_factor() / 1.25)

    def reset_zoom(self) -> None:
        self._zoom = -1.0
        self._apply_fit()
        self.update()

    # ----- internal helpers -----
    def _placeholder(self, text: str) -> None:
        pm = QPixmap(self.size())
        pm.fill(QColor("#0C0A08"))
        p = QPainter(pm)
        p.setPen(QColor("#B1A096"))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        self._pixmap = pm

    def _apply_fit(self) -> None:
        if self._pixmap is None:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        if iw == 0 or ih == 0 or cw == 0 or ch == 0:
            return
        z = min(cw / iw, ch / ih)
        self._fit_zoom = max(0.05, z)
        self._offset = QPointF(0, 0)
        if self._zoom < 0:
            self._zoom = self._fit_zoom

    def _clamp_offset(self) -> None:
        if self._pixmap is None:
            return
        iw = self._pixmap.width() * self._zoom
        ih = self._pixmap.height() * self._zoom
        cw, ch = self.width(), self.height()
        max_x = max(0.0, (iw - cw) / 2)
        max_y = max(0.0, (ih - ch) / 2)
        ox = max(-max_x, min(max_x, self._offset.x()))
        oy = max(-max_y, min(max_y, self._offset.y()))
        self._offset = QPointF(ox, oy)

    # ----- events -----
    def resizeEvent(self, e: QResizeEvent) -> None:
        if self._zoom < 0 or self._pixmap is not None:
            self._apply_fit()
        super().resizeEvent(e)

    def paintEvent(self, e: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0C0A08"))
        if self._pixmap is None:
            p.setPen(QColor("#B1A096"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无图片")
            return
        z = self.zoom_factor()
        iw, ih = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        draw_w, draw_h = iw * z, ih * z
        x = (cw - draw_w) / 2 + self._offset.x()
        y = (ch - draw_h) / 2 + self._offset.y()
        target = QRectF(x, y, draw_w, draw_h)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, z < 4)
        p.drawPixmap(target, self._pixmap, QRectF(0, 0, iw, ih))

    def _resolve_wheel_action(self) -> str:
        """Determine whether wheel should zoom or switch."""
        from ...core.settings_store import ProjectSettingsStore
        action = "zoom"
        try:
            win = self.window()
            if hasattr(win, "settings") and isinstance(win.settings, ProjectSettingsStore):
                action = win.settings.get("wheel_action", "zoom")
        except Exception:
            pass
        return action

    def _resolve_wheel_modifier(self) -> Qt.KeyboardModifier:
        from ...core.settings_store import ProjectSettingsStore
        try:
            win = self.window()
            if hasattr(win, "settings") and isinstance(win.settings, ProjectSettingsStore):
                m = win.settings.get("wheel_modifier_for_alt", "Ctrl")
                return {"Ctrl": Qt.KeyboardModifier.ControlModifier,
                        "Shift": Qt.KeyboardModifier.ShiftModifier,
                        "Alt": Qt.KeyboardModifier.AltModifier}.get(m,
                        Qt.KeyboardModifier.ControlModifier)
        except Exception:
            pass
        return Qt.KeyboardModifier.ControlModifier

    def wheelEvent(self, e: QWheelEvent) -> None:
        if self._pixmap is None:
            return
        action = self._resolve_wheel_action()
        mods = e.modifiers()
        delta = e.angleDelta().y()
        if action == "switch_image":
            alt_mod = self._resolve_wheel_modifier()
            if mods & alt_mod:
                self._wheel_zoom(delta)
            else:
                self.wheelSwitchRequested.emit(1 if delta > 0 else -1)
                e.accept()
        else:
            self._wheel_zoom(delta)
            e.accept()

    def _wheel_zoom(self, delta: int) -> None:
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self._pixmap is not None:
            self._dragging = True
            self._last_pos = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._dragging and self._pixmap is not None:
            dx = e.position().x() - self._last_pos.x()
            dy = e.position().y() - self._last_pos.y()
            self._offset += QPointF(dx, dy)
            self._last_pos = e.position()
            self._clamp_offset()
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        super().keyPressEvent(e)

    def sizeHint(self) -> QSize:
        return QSize(800, 600)
