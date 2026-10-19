"""Custom frameless title bar.

Replaces the OS-native title bar with a hand-drawn one that supports
drag, double-click maximise, edge resize, and preserves multi-monitor
+ native taskbar behaviour.

Important: TitleBar.parent MUST be the FramelessWindow itself, not the
outer container. If the parent is the outer container, dragging only
moves the inner container inside the window instead of moving the
window. We therefore pass `self` (the FramelessWindow) into TitleBar
and use it as the drag target.
"""
from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QMainWindow,
    QSizePolicy, QMenuBar,
)

from .. import colors as C
from ..icon import load_app_icon
from .win_hit_test import enable_native_resize_border, native_hit_test


class TitleBar(QWidget):
    """Hand-drawn title bar that drives window move / min / max / close.

    Must be parented to the QMainWindow (or any top-level widget you want
    to drag). The parent is used as the drag target.
    """

    minimiseRequested = Signal()
    maximiseToggleRequested = Signal()
    closeRequested = Signal()

    HEIGHT = 36

    def __init__(self, window, title: str = ""):
        super().__init__(window)
        # The window we drive. We capture this so that even if Qt reparents
        # us (it doesn't, but defensive), drag still targets the window.
        self._window = window
        self._drag_pos = None
        self._pressed_on_bar = False
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("FramelessTitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        self._icon_lbl = QLabel(self)
        self._icon_lbl.setFixedSize(20, 20)
        pm = load_app_icon().pixmap(QSize(20, 20))
        self._icon_lbl.setPixmap(pm)
        self._icon_lbl.setStyleSheet("background: transparent;")
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._icon_lbl)

        self._title_lbl = QLabel(title or (window.windowTitle() if window else ""), self)
        self._title_lbl.setStyleSheet(
            f"color: {C.TEXT_PRIMARY}; background: transparent; font-weight: 600; font-size: 13px;"
        )
        self._title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._title_lbl, 1)

        btn_style = (
            "QPushButton { background: transparent; color: %s; border: 0; }"
            "QPushButton:hover { background: %s; color: %s; }"
            "QPushButton:pressed { background: %s; }"
        ) % (C.TEXT_SECONDARY, C.BG_PANEL_HOVER, C.TEXT_PRIMARY, C.BG_PANEL_PRESSED)

        self._min_btn = QPushButton("\u2212", self)
        self._min_btn.setFixedSize(44, self.HEIGHT)
        self._min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min_btn.setStyleSheet(btn_style)
        self._min_btn.clicked.connect(self.minimiseRequested.emit)
        layout.addWidget(self._min_btn)

        self._max_btn = QPushButton("\u25A2", self)
        self._max_btn.setFixedSize(44, self.HEIGHT)
        self._max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._max_btn.setStyleSheet(btn_style)
        self._max_btn.clicked.connect(self.maximiseToggleRequested.emit)
        layout.addWidget(self._max_btn)

        close_style = (
            "QPushButton { background: transparent; color: %s; border: 0; }"
            "QPushButton:hover { background: %s; color: %s; }"
            "QPushButton:pressed { background: #8C4F3D; }"
        ) % (C.TEXT_SECONDARY, C.ACCENT_RUST, C.TEXT_PRIMARY)
        self._close_btn = QPushButton("\u2715", self)
        self._close_btn.setFixedSize(48, self.HEIGHT)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(close_style)
        self._close_btn.clicked.connect(self.closeRequested.emit)
        layout.addWidget(self._close_btn)

        self.setStyleSheet(
            f"#FramelessTitleBar {{ background-color: {C.BG_PANEL}; border-bottom: 1px solid {C.DIVIDER}; }}"
        )

    def setWindowTitle(self, title):
        self._title_lbl.setText(title)

    def setMaximisedIcon(self, is_max):
        self._max_btn.setText("\u2750" if is_max else "\u25A2")

    # ---- Drag handling ----
    def _resolve_window(self) -> Optional[QWidget]:
        """Return the top-level window we should drag."""
        w = self._window
        if w is None:
            return None
        return w.window()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            win = self._resolve_window()
            if win is None:
                return super().mousePressEvent(e)
            self._pressed_on_bar = True
            # frameGeometry() so multi-monitor / non-maximised origin is right.
            self._drag_pos = e.globalPosition().toPoint() - win.pos()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is None or not self._pressed_on_bar:
            return super().mouseMoveEvent(e)
        win = self._resolve_window()
        if win is None:
            return super().mouseMoveEvent(e)
        if win.isMaximized():
            win.showNormal()
            self._drag_pos = QPoint(win.width() // 2, self.HEIGHT // 2)
        win.move(e.globalPosition().toPoint() - self._drag_pos)
        e.accept()

    def mouseReleaseEvent(self, e):
        self._pressed_on_bar = False
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.maximiseToggleRequested.emit()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)


class FramelessWindow(QMainWindow):
    """A QMainWindow with a hand-drawn title bar and edge-resize support.

    Structure
    ---------
    QMainWindow
      +-- title_bar  (parented directly to the window so dragging moves it)
      +-- centralWidget (_outer) = [title_bar | menubar_holder | central_holder]

    Notes
    -----
    The QMainWindow's native menu bar is hidden. The custom ``menuBar()``
    override returns a QMenuBar hosted inside the title-bar area.
    """

    EDGE_MARGIN = 6

    def __init__(self, *args, title: str = "", **kwargs):
        # Bypass any subclass __init__ recursion: call QMainWindow directly.
        QMainWindow.__init__(self, *args, **kwargs)
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
        )

        # Pre-create layout primitives BEFORE any subclass-overridden helper
        # (like menuBar()) could be triggered by Qt internals.
        self._outer = QWidget()
        self._outer.setObjectName("FramelessOuter")
        self._outer.setStyleSheet(
            f"#FramelessOuter {{ background-color: {C.BG_BASE}; }}"
        )
        outer_layout = QVBoxLayout(self._outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # TitleBar is parented to the WINDOW so dragging moves the window.
        self.title_bar = TitleBar(self, title=title)
        outer_layout.addWidget(self.title_bar)

        # Optional app-level menubar slot.
        self._app_menubar_holder = QWidget(self._outer)
        self._app_menubar_holder.setObjectName("FramelessMenuBarHolder")
        self._app_menubar_holder.setStyleSheet(
            f"#FramelessMenuBarHolder {{ background-color: {C.BG_PANEL}; border-bottom: 1px solid {C.DIVIDER}; }}"
        )
        self._app_menubar_layout = QHBoxLayout(self._app_menubar_holder)
        self._app_menubar_layout.setContentsMargins(8, 0, 8, 0)
        self._app_menubar_layout.setSpacing(0)
        outer_layout.addWidget(self._app_menubar_holder)

        # Body container for the user's setCentralWidget() call.
        self._central_holder = QWidget(self._outer)
        self._central_holder.setStyleSheet("background: transparent;")
        outer_layout.addWidget(self._central_holder, 1)

        # Install _outer as the real central widget. We bypass our override
        # by calling QMainWindow.setCentralWidget directly; our override
        # expects a body widget and would route through _central_holder.
        QMainWindow.setCentralWidget(self, self._outer)

        # Hide the native QMainWindow menu bar (the empty default one) so it
        # does not appear at the very top of the window. Application code
        # calls self.menuBar(), which our override routes to the custom
        # holder inside the title bar area.
        try:
            QMainWindow.menuBar(self).setVisible(False)
        except Exception:
            pass

        # Connect title-bar buttons.
        self.title_bar.minimiseRequested.connect(self.showMinimized)
        self.title_bar.maximiseToggleRequested.connect(self._toggle_max)
        self.title_bar.closeRequested.connect(self.close)

        self._resizing = False
        self._resize_edges = Qt.Edge(0)
        self._resize_start_pos = QPoint()
        self._resize_start_geom = QRect()
        self.setMouseTracking(True)
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

    # ---- Title / menubar plumbing ----
    def setWindowTitle(self, title):
        super().setWindowTitle(title)
        if hasattr(self, "title_bar"):
            self.title_bar.setWindowTitle(title)

    def menuBar(self):
        """Return the custom title-bar-area menubar (lazily created)."""
        mb = getattr(self, "_app_menubar", None)
        if mb is None:
            mb = QMenuBar(self._app_menubar_holder)
            mb.setStyleSheet(
                f"QMenuBar {{ background: transparent; color: {C.TEXT_PRIMARY}; }}"
                f"QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 4px; }}"
                f"QMenuBar::item:selected {{ background: {C.BG_PANEL_HOVER}; }}"
                f"QMenuBar::item:pressed {{ background: {C.BG_PANEL_PRESSED}; }}"
            )
            self._app_menubar_layout.addWidget(mb)
            self._app_menubar = mb
        return mb

    def setCentralWidget(self, w):
        """Insert ``w`` into the body area (between menubar and status bar)."""
        layout = self._central_holder.layout()
        if layout is None:
            layout = QVBoxLayout(self._central_holder)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        old = layout.takeAt(0)
        if old is not None:
            old_widget = old.widget()
            if old_widget is not None:
                old_widget.setParent(None)
        layout.addWidget(w)

    def centralWidget(self):
        layout = self._central_holder.layout() if self._central_holder else None
        if layout is None:
            return None
        item = layout.itemAt(0)
        if item is None:
            return None
        return item.widget()

    # ---- Maximise / restore ----
    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
            self.title_bar.setMaximisedIcon(False)
        else:
            self.showMaximized()
            self.title_bar.setMaximisedIcon(True)

    def changeEvent(self, e):
        if e.type() == e.Type.WindowStateChange:
            self.title_bar.setMaximisedIcon(self.isMaximized())
        super().changeEvent(e)

    # ---- Edge resize ----
    def _detect_edge(self, pos):
        edges = Qt.Edge(0)
        m = self.EDGE_MARGIN
        rect = self.rect()
        if pos.x() <= m:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= rect.width() - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() >= rect.height() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, e):
        if self.isMaximized():
            return super().mouseMoveEvent(e)
        if self._resizing:
            self._perform_resize(e.globalPosition().toPoint())
            return
        edges = self._detect_edge(e.position().toPoint())
        if edges & Qt.Edge.LeftEdge and edges & Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & Qt.Edge.RightEdge and edges & Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges & Qt.Edge.LeftEdge or edges & Qt.Edge.RightEdge:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & Qt.Edge.BottomEdge:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            edges = self._detect_edge(e.position().toPoint())
            if edges:
                self._resizing = True
                self._resize_edges = edges
                self._resize_start_pos = e.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = False
            self._resize_edges = Qt.Edge(0)
            self.unsetCursor()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _perform_resize(self, global_pos):
        delta = global_pos - self._resize_start_pos
        geom = QRect(self._resize_start_geom)
        min_w = max(self.minimumWidth(), 320)
        min_h = max(self.minimumHeight(), 240)
        if self._resize_edges & Qt.Edge.LeftEdge:
            new_x = geom.x() + delta.x()
            new_w = geom.width() - delta.x()
            if new_w < min_w:
                new_x -= (min_w - new_w)
                new_w = min_w
            geom.setX(new_x)
            geom.setWidth(new_w)
        if self._resize_edges & Qt.Edge.RightEdge:
            geom.setWidth(max(min_w, geom.width() + delta.x()))
        if self._resize_edges & Qt.Edge.BottomEdge:
            geom.setHeight(max(min_h, geom.height() + delta.y()))
        self.setGeometry(geom)
