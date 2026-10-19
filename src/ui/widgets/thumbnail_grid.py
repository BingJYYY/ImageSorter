"""Thumbnail grid with virtualized rendering for thousands of images."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional, Callable

from PySide6.QtCore import Qt, QRect, QSize, Signal, QPoint
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QListWidget, QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem,
    QStyle, QApplication,
)
from PySide6.QtCore import QSize as QCoreSize

from ...core.thumbnail import ThumbnailCache
from ...core.image_loader import open_for_display


class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, thumb_size: int, parent=None):
        super().__init__(parent)
        self.thumb_size = thumb_size

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        ts = self.thumb_size
        return QSize(ts + 16, ts + 36)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.fillRect(rect, QColor(208, 163, 114, 50))
        elif hover:
            painter.fillRect(rect, QColor(20, 19, 17))
        # Image
        pm = index.data(Qt.ItemDataRole.UserRole)
        if pm and isinstance(pm, QPixmap):
            ts = self.thumb_size
            x = rect.x() + (rect.width() - ts) // 2
            y = rect.y() + 8
            painter.drawPixmap(x, y, ts, ts, pm)
        # Filename
        name = index.data(Qt.ItemDataRole.UserRole + 1) or ""
        painter.setPen(QColor("#F3E2DB") if selected else QColor("#B1A096"))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        text_rect = QRect(rect.x() + 6, rect.bottom() - 24, rect.width() - 12, 20)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextSingleLine,
                         QFontMetrics(font).elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width()))
        painter.restore()


class ThumbnailGrid(QListWidget):
    """Virtualized grid of thumbnails. Lazy-loads via ThumbnailCache in background."""

    itemActivated = Signal(int)  # index

    def __init__(self, cache: ThumbnailCache, parent=None):
        super().__init__(parent)
        self._cache = cache
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ts = self._cache.max_dimension
        self.setGridSize(QSize(ts + 24, ts + 44))
        self.setItemDelegate(ThumbDelegate(ts, self))
        self._thumb_size = ts

    def populate(self, paths: List[Path]) -> None:
        self.clear()
        for p in paths:
            it = QListWidgetItem()
            it.setData(Qt.ItemDataRole.UserRole, None)
            it.setData(Qt.ItemDataRole.UserRole + 1, Path(p).name)
            it.setData(Qt.ItemDataRole.UserRole + 2, str(p))
            self.addItem(it)

    def update_thumb(self, row: int, path: Path) -> None:
        if row < 0 or row >= self.count():
            return
        it = self.item(row)
        cached = self._cache.get_or_generate(path)
        if cached is not None and cached.exists():
            pm = QPixmap(str(cached))
            if not pm.isNull():
                it.setData(Qt.ItemDataRole.UserRole, pm)

    def set_current_row(self, row: int) -> None:
        if 0 <= row < self.count():
            self.setCurrentRow(row)
            self.scrollToItem(self.item(row), QListWidget.ScrollHint.PositionAtCenter)
