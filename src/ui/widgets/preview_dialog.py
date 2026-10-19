"""Preview dialog: lazily loaded thumbnail wall for choosing a start point."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QImageReader, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from .. import colors as C
from ...core.thumbnail import ThumbnailCache
from .button_style import apply_icon_button
from .frameless_dialog import FramelessDialog


THUMB_W = 160
THUMB_H = 120
COLS = 6
PAGE_SIZE = 120


class PreviewDialog(FramelessDialog):
    """Pick the starting image for a filter session."""

    startingIndexChosen = Signal(int)

    def __init__(self, paths: List[Path], thumb_cache: Optional[ThumbnailCache],
                 current_index: int = -1, parent: Optional[QWidget] = None):
        super().__init__("预览", parent)
        self.setMinimumSize(900, 600)
        self.resize(1100, 760)
        self._paths = list(paths)
        self._cache = thumb_cache
        self._chosen_index = -1
        self._current_index = current_index
        self._page = max(0, current_index // PAGE_SIZE) if current_index >= 0 else 0
        self._labels: List[QLabel] = []
        self._page_start = 0
        self._queue: List[Tuple[QLabel, Path, int]] = []
        self._built = False
        self._page_token = 0
        self._build()
        self._show_page(self._page)

    def _build(self) -> None:
        root = self.body_layout
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        info = QLabel(f"共 {len(self._paths)} 张 · 单击缩略图选择起始位置")
        info.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 12px;")
        header.addWidget(info)
        header.addStretch(1)
        self._loading_label = QLabel("")
        self._loading_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 11px;"
        )
        header.addWidget(self._loading_label)
        self._prev_page_btn = QPushButton("‹")
        apply_icon_button(self._prev_page_btn, 28)
        self._prev_page_btn.clicked.connect(lambda: self._go_page(self._page - 1))
        header.addWidget(self._prev_page_btn)
        self._page_label = QLabel()
        self._page_label.setStyleSheet(
            f"color: {C.TEXT_PRIMARY}; font-size: 12px; padding: 0 6px;"
        )
        header.addWidget(self._page_label)
        self._next_page_btn = QPushButton("›")
        apply_icon_button(self._next_page_btn, 28)
        self._next_page_btn.clicked.connect(lambda: self._go_page(self._page + 1))
        header.addWidget(self._next_page_btn)
        root.addLayout(header)

        self._wall = QWidget()
        self._grid = QGridLayout(self._wall)
        self._grid.setSpacing(8)
        self._grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._wall)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent;"
            f" border: 1px solid {C.BORDER}; border-radius: 10px;"
            " padding: 8px; }}"
        )
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        from_first = QPushButton("从第一张开始")
        from_first.setProperty("accent", "ghost")
        from_first.clicked.connect(lambda: self._choose(0))
        footer.addWidget(from_first)
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        root.addLayout(footer)

    def _go_page(self, page: int) -> None:
        pages = max(1, (len(self._paths) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(pages - 1, page))
        if page == self._page and self._built:
            return
        self._page = page
        self._show_page(page)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._labels = []
        self._queue = []

    def _show_page(self, page: int) -> None:
        self._built = True
        self._page_token += 1
        token = self._page_token
        self._clear_grid()
        start = page * PAGE_SIZE
        end = min(len(self._paths), start + PAGE_SIZE)
        self._page_start = start
        pages = max(1, (len(self._paths) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page_label.setText(f"{page + 1} / {pages}")
        self._prev_page_btn.setEnabled(page > 0)
        self._next_page_btn.setEnabled(page + 1 < pages)

        for offset, idx in enumerate(range(start, end)):
            path = self._paths[idx]
            label = QLabel()
            label.setFixedSize(THUMB_W, THUMB_H)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.setText(self._short_name(path))
            label.setStyleSheet(self._label_style(idx == self._current_index))
            label.mousePressEvent = self._make_click_handler(idx)
            self._grid.addWidget(label, offset // COLS, offset % COLS)
            self._labels.append(label)
            self._queue.append((label, path, idx))

        self._loading_label.setText(
            f"正在加载缩略图 0 / {len(self._queue)}" if self._queue else ""
        )
        QTimer.singleShot(0, lambda: self._load_next_batch(token))

    def _short_name(self, path: Path) -> str:
        name = path.name
        return name if len(name) <= 18 else name[:15] + "…"

    def _label_style(self, selected: bool) -> str:
        border = C.ACCENT_GOLD if selected else C.BORDER
        return (
            f"background-color: {C.BG_PANEL};"
            f" border: 2px solid {border}; border-radius: 8px;"
            f" color: {C.TEXT_SECONDARY}; font-size: 11px; padding: 4px;"
        )

    def _load_next_batch(self, token: int = -1) -> None:
        if token != -1 and token != self._page_token:
            return
        if not self._queue:
            self._loading_label.setText("")
            return
        batch = 0
        while self._queue and batch < 3:
            label, path, idx = self._queue.pop(0)
            pixmap = self._pixmap_for(path)
            if pixmap is not None and not pixmap.isNull():
                label.setText("")
                label.setPixmap(pixmap)
                label.setStyleSheet(self._label_style(idx == self._current_index))
            else:
                label.setText(f"{self._short_name(path)}\n（无法生成缩略图）")
            batch += 1
        total = len(self._labels)
        remaining = len(self._queue)
        if remaining:
            self._loading_label.setText(
                f"正在加载缩略图 {total - remaining} / {total}"
            )
            QTimer.singleShot(0, lambda: self._load_next_batch(token))
        else:
            self._loading_label.setText("")

    def _pixmap_for(self, path: Path) -> Optional[QPixmap]:
        if self._cache is not None:
            thumb = self._cache.get_or_generate(path)
            pixmap = self._pixmap_from_file(thumb) if thumb else None
            if pixmap is None:
                thumb = self._cache.get_or_generate(path, force_regen=True)
                pixmap = self._pixmap_from_file(thumb) if thumb else None
            if pixmap is not None:
                return pixmap
        return self._direct_pixmap(path)

    def _pixmap_from_file(self, path: Path) -> Optional[QPixmap]:
        try:
            pixmap = QPixmap(str(path))
        except Exception:
            return None
        if pixmap.isNull():
            return None
        return pixmap.scaled(
            THUMB_W - 4, THUMB_H - 4,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _direct_pixmap(self, path: Path) -> Optional[QPixmap]:
        try:
            reader = QImageReader(str(path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid() and not size.isEmpty():
                scale = min(
                    (THUMB_W * 2) / size.width(),
                    (THUMB_H * 2) / size.height(),
                )
                if scale < 1:
                    reader.setScaledSize(
                        QSize(
                            max(1, int(size.width() * scale)),
                            max(1, int(size.height() * scale)),
                        )
                    )
            image = reader.read()
            if image.isNull():
                return None
            return QPixmap.fromImage(image).scaled(
                THUMB_W - 4, THUMB_H - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        except Exception:
            return None

    def _make_click_handler(self, idx: int):
        def handler(event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._choose(idx)
        return handler

    def _choose(self, idx: int) -> None:
        self._chosen_index = idx
        self.startingIndexChosen.emit(idx)
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def chosen_index(self) -> int:
        return self._chosen_index


class CategoryPanel(QFrame):
    """A floating panel that lists categories + their hotkeys."""

    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.setObjectName("CategoryPanel")
        self.setStyleSheet(
            f"#CategoryPanel {{ background-color: {C.BG_PANEL};"
            f" border: 1px solid {C.BORDER}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        title = QLabel("分类 / 快捷键")
        title.setStyleSheet(
            f"color: {C.ACCENT_GOLD}; font-weight: 700; font-size: 13px;"
        )
        layout.addWidget(title)
        if not categories:
            empty = QLabel("（尚未配置分类）")
            empty.setStyleSheet(
                f"color: {C.TEXT_MUTED}; font-size: 12px; padding: 6px;"
            )
            layout.addWidget(empty)
        for cat in categories:
            row = QHBoxLayout()
            key_lbl = QLabel(cat.key)
            key_lbl.setFixedSize(28, 28)
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_lbl.setStyleSheet(
                f"color: {C.BG_BASE}; background-color: {C.ACCENT_GOLD};"
                " border-radius: 14px; font-weight: 700;"
            )
            row.addWidget(key_lbl)
            name_lbl = QLabel(cat.name)
            name_lbl.setStyleSheet(
                f"color: {C.TEXT_PRIMARY}; font-size: 13px;"
            )
            row.addWidget(name_lbl, 1)
            dir_lbl = QLabel(cat.target_dir)
            dir_lbl.setStyleSheet(
                f"color: {C.TEXT_MUTED}; font-size: 11px;"
            )
            dir_lbl.setWordWrap(False)
            dir_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.NoTextInteraction
            )
            row.addWidget(dir_lbl, 2)
            layout.addLayout(row)
