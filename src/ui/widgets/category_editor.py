"""Category editor: a compact one-row widget for key + name + folder.

Used both in the new-project wizard and the project settings dialog.
Rows are added/removed dynamically via the surrounding list widget.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QFileDialog, QInputDialog, QMessageBox, QScrollArea,
)

from ...core.project import Category
from .key_capture import KeyCaptureButton
from .button_style import apply_gold_button, apply_icon_button
from .. import colors as C


class CategoryRow(QFrame):
    """A single category row: key badge + capture + name + folder + delete."""

    changed = Signal()
    removeRequested = Signal(object)  # emits self

    def __init__(self, key: str = "", name: str = "", target_dir: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("CategoryRow")
        self.setStyleSheet(
            f"#CategoryRow {{ background-color: {C.BG_PANEL}; border: 1px solid {C.BORDER}; border-radius: 10px; }}"
            f"#CategoryRow:hover {{ border: 1px solid {C.DIVIDER_STRONG}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Key badge (golden circle, label only)
        self.badge = QLabel(key or "?")
        self.badge.setFixedSize(32, 32)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setStyleSheet(
            f"color: {C.BG_BASE}; background-color: {C.ACCENT_GOLD}; border-radius: 16px; font-weight: 700;"
        )
        layout.addWidget(self.badge)

        # Key capture button
        self.key_btn = KeyCaptureButton(initial=key, placeholder="点击设置按键")
        self.key_btn.setFixedWidth(140)
        self.key_btn.keyChanged.connect(self._on_key_changed)
        layout.addWidget(self.key_btn)

        # Name input
        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("分类名称")
        self.name_input.setMaximumWidth(180)
        self.name_input.textChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.name_input)

        # Vertical separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {C.DIVIDER};")
        sep.setFixedHeight(20)
        layout.addWidget(sep)

        # Folder picker
        self.dir_input = QLineEdit(target_dir)
        self.dir_input.setPlaceholderText("选择此分类的目标文件夹")
        self.dir_input.textChanged.connect(lambda _: self.changed.emit())
        layout.addWidget(self.dir_input, 1)

        browse = QPushButton("浏览...")
        browse.setProperty("accent", "ghost")
        browse.clicked.connect(self._pick_dir)
        layout.addWidget(browse)

        # Delete button (removes the row)
        del_btn = QPushButton("\u2715")  # X
        apply_icon_button(del_btn, 28)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setToolTip("删除此分类")
        del_btn.clicked.connect(lambda: self.removeRequested.emit(self))
        layout.addWidget(del_btn)

    # ---- Public API ----
    def get_category(self) -> Optional[Category]:
        key = (self.key_btn.value() or "").strip()
        name = self.name_input.text().strip()
        target = self.dir_input.text().strip()
        if not key:
            return None
        if not target:
            return None  # need a folder to be usable
        if not name:
            name = f"分类 {key}"
        return Category(key=key, name=name, target_dir=target, enabled=True)

    def set_key(self, key: str) -> None:
        self.key_btn.setValue(key)
        self.badge.setText(key or "?")

    def set_name(self, name: str) -> None:
        self.name_input.setText(name)

    def set_target_dir(self, path: str) -> None:
        self.dir_input.setText(path)

    def key(self) -> str:
        return self.key_btn.value() or ""

    # ---- Internal ----
    def _on_key_changed(self, new_key: str) -> None:
        self.badge.setText(new_key or "?")
        self.changed.emit()

    def _pick_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择分类目标目录")
        if d:
            self.dir_input.setText(d)


class CategoryListWidget(QWidget):
    """Container widget that owns a list of CategoryRow instances.

    Provides:
      - a scrollable list of rows
      - an "+ 新建分类" button that appends a blank row and focuses the key capture
      - collect/get to gather all rows back into Category objects
    """

    rowsChanged = Signal()

    def __init__(self, initial: Optional[List[Category]] = None, parent=None):
        super().__init__(parent)
        self._rows: List[CategoryRow] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # Top action row: the add button stays pinned above the scroll area so
        # it can never be clipped by a short window.
        actions = QHBoxLayout()
        self._hint = QLabel("点击 + 新建分类 一个一个添加。")
        self._hint.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px;")
        actions.addWidget(self._hint, 1)
        add_btn = QPushButton("+ 新建分类")
        apply_gold_button(add_btn, compact=True)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        actions.addWidget(add_btn)
        root.addLayout(actions)

        # Scrollable row container
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMinimumHeight(140)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: 1px solid {C.BORDER}; border-radius: 10px; padding: 6px; }}"
        )
        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._inner)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._inner)
        root.addWidget(self._scroll, 1)

        if initial:
            for c in initial:
                self._append_row(c.key, c.name, c.target_dir)

    # ---- Public API ----
    def rows(self) -> List[CategoryRow]:
        return list(self._rows)

    def collect(self) -> List[Category]:
        cats: List[Category] = []
        for row in self._rows:
            c = row.get_category()
            if c is not None:
                cats.append(c)
        return cats

    def clear(self) -> None:
        for row in self._rows:
            self._list_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self.rowsChanged.emit()

    # ---- Internal ----
    def _on_add_clicked(self) -> None:
        row = self._append_row("", "", "")
        row.key_btn._on_click()  # start recording immediately
        self.rowsChanged.emit()

    def _append_row(self, key: str, name: str, target_dir: str) -> CategoryRow:
        row = CategoryRow(key, name, target_dir, self._inner)
        row.changed.connect(self.rowsChanged.emit)
        row.removeRequested.connect(self._on_remove)
        # Insert before the trailing stretch
        idx = self._list_layout.count() - 1
        self._list_layout.insertWidget(idx, row)
        self._rows.append(row)
        return row

    def _on_remove(self, row: CategoryRow) -> None:
        if row not in self._rows:
            return
        reply = QMessageBox.question(
            self,
            "删除分类",
            "确定要从项目中删除这个分类吗？\n（已经分类到此文件夹的图片不会移动。）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._rows.remove(row)
        self._list_layout.removeWidget(row)
        row.deleteLater()
        self.rowsChanged.emit()
