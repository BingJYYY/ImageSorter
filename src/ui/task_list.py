"""Project list home page (Photoshop-style layout, dark warm theme)."""

from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QColor, QPainter, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QGridLayout, QSizePolicy, QMenu, QInputDialog,
    QMessageBox, QFileDialog,
)

from ..core.project import Project, ProjectStore, STATUS_IN_PROGRESS, STATUS_COMPLETED
from .widgets.button_style import apply_gold_button
from . import colors as C


class ProjectCard(QFrame):
    clicked = Signal(str)
    openInNewWindow = Signal(str)
    deleteRequested = Signal(str)
    renameRequested = Signal(str)
    editRequested = Signal(str)
    markCompleted = Signal(str)
    markInProgress = Signal(str)
    openSourceDir = Signal(str)
    exportRequested = Signal(str)
    projectSettingsRequested = Signal(str)
    coverRequested = Signal(str)

    def __init__(self, meta: dict, parent=None):
        super().__init__(parent)
        self.meta = meta
        self.setObjectName("ProjectCard")
        self.setStyleSheet(f"""
            QFrame#ProjectCard {{
                background-color: {C.BG_PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
            QFrame#ProjectCard:hover {{
                border: 1px solid {C.ACCENT_GOLD};
                background-color: {C.BG_PANEL_HOVER};
            }}
        """)
        self.setFixedSize(280, 220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(8)

        # Cover
        cover = QLabel()
        cover.setFixedHeight(140)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setStyleSheet(f"""
            background-color: {C.BG_RAISED};
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            color: {C.TEXT_MUTED};
        """)
        cover_text = "无封面"
        cover_path = self.meta.get("cover_image")
        if cover_path and Path(cover_path).exists():
            pm = QPixmap(str(cover_path))
            if not pm.isNull():
                pm = pm.scaled(280, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
                cover.setPixmap(pm)
                cover_text = ""
        cover.setText(cover_text)
        layout.addWidget(cover)

        # Title + status
        row = QHBoxLayout()
        row.setContentsMargins(12, 0, 12, 0)
        name = QLabel(self.meta.get("name", "未命名"))
        name.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-weight: 600; font-size: 14px;")
        row.addWidget(name, 1)
        status = self.meta.get("status", STATUS_IN_PROGRESS)
        badge = QLabel("进行中" if status == STATUS_IN_PROGRESS else "已完成")
        badge.setStyleSheet(
            f"color: {C.BG_BASE}; background-color: {C.ACCENT_GOLD};"
            "padding: 2px 8px; border-radius: 8px; font-size: 11px;"
            if status == STATUS_IN_PROGRESS else
            f"color: {C.TEXT_PRIMARY}; background-color: {C.BG_PANEL_PRESSED};"
            "padding: 2px 8px; border-radius: 8px; font-size: 11px;"
        )
        row.addWidget(badge)
        layout.addLayout(row)

        # Progress info
        info = QLabel(self._progress_text())
        info.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 11px; padding: 0 12px;")
        layout.addWidget(info)

    def _progress_text(self) -> str:
        cur = self.meta.get("current_index", -1)
        total = self.meta.get("total", 0)
        if cur < 0 or total == 0:
            return "尚未开始"
        return f"{cur + 1} / {total}"

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.meta.get("id", ""))
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(e.position().toPoint())

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("打开", lambda: self.clicked.emit(self.meta["id"]))
        menu.addAction("编辑项目", lambda: self.editRequested.emit(self.meta["id"]))
        menu.addAction("项目设置", lambda: self.projectSettingsRequested.emit(self.meta["id"]))
        menu.addAction("设置封面…", lambda: self.coverRequested.emit(self.meta["id"]))
        menu.addSeparator()
        if self.meta.get("status") == STATUS_IN_PROGRESS:
            menu.addAction("标记为已完成", lambda: self.markCompleted.emit(self.meta["id"]))
        else:
            menu.addAction("标记为进行中", lambda: self.markInProgress.emit(self.meta["id"]))
        menu.addSeparator()
        menu.addAction("重命名", lambda: self.renameRequested.emit(self.meta["id"]))
        menu.addAction("打开源目录", lambda: self.openSourceDir.emit(self.meta["id"]))
        menu.addAction("导出/备份", lambda: self.exportRequested.emit(self.meta["id"]))
        menu.addAction("在新窗口打开", lambda: self.openInNewWindow.emit(self.meta["id"]))
        menu.addSeparator()
        menu.addAction("删除", lambda: self.deleteRequested.emit(self.meta["id"]))
        menu.exec(self.mapToGlobal(pos))


class TaskListPage(QWidget):
    """Photoshop-style project home with two tabs: 进行中 / 已完成."""

    openProject = Signal(str)                 # project id
    openProjectInNewWindow = Signal(str)
    createNewProject = Signal()
    editProject = Signal(str)
    deleteProject = Signal(str)
    renameProject = Signal(str)
    markProjectCompleted = Signal(str)
    markProjectInProgress = Signal(str)
    openProjectSourceDir = Signal(str)
    exportProject = Signal(str)
    projectSettingsRequested = Signal(str)
    setCoverRequested = Signal(str)

    def __init__(self, project_store: ProjectStore, parent=None):
        super().__init__(parent)
        self.store = project_store
        self._current_tab = "in_progress"
        self._tab_buttons: Dict[str, QPushButton] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Top app bar ----
        bar = QFrame()
        bar.setFixedHeight(64)
        bar.setStyleSheet(f"""
            QFrame {{ background-color: {C.BG_BASE}; border-bottom: 1px solid {C.DIVIDER}; }}
        """)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(24, 0, 24, 0)
        logo = QLabel("图片筛选")
        logo.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; letter-spacing: 2px;")
        bl.addWidget(logo)
        sub = QLabel("  LOCAL SORTING ENGINE")
        sub.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px; letter-spacing: 3px;")
        bl.addWidget(sub)
        bl.addStretch(1)
        new_btn = QPushButton("+ 新建项目")
        apply_gold_button(new_btn, compact=True)
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self.createNewProject.emit)
        bl.addWidget(new_btn)
        root.addWidget(bar)

        # ---- Tabs (In progress / Completed) ----
        tab_bar = QFrame()
        tab_bar.setFixedHeight(54)
        tab_bar.setStyleSheet(f"background-color: {C.BG_BASE}; border-bottom: 1px solid {C.DIVIDER};")
        tbl = QHBoxLayout(tab_bar)
        tbl.setContentsMargins(24, 0, 24, 0)
        tbl.addWidget(self._make_tab_button("进行中", "in_progress", True))
        tbl.addWidget(self._make_tab_button("已完成", "completed", False))
        tbl.addStretch(1)
        root.addWidget(tab_bar)

        # ---- Body ----
        self._body_stack = QVBoxLayout()
        self._body_stack.setContentsMargins(24, 24, 24, 24)
        root.addLayout(self._body_stack, 1)

        # Scrollable container
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._grid = QGridLayout(self._inner)
        self._grid.setSpacing(16)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._inner)
        self._body_stack.addWidget(self._scroll)

    def _make_tab_button(self, text: str, tab_id: str, active: bool) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setProperty("tabId", tab_id)
        b.clicked.connect(lambda: self._switch_tab(tab_id))
        self._tab_buttons[tab_id] = b
        self._apply_tab_style(b, active)
        return b

    def _apply_tab_style(self, b: QPushButton, active: bool) -> None:
        color = C.ACCENT_GOLD if active else C.TEXT_SECONDARY
        b.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {color};
                border: 0;
                border-bottom: 2px solid {C.ACCENT_GOLD if active else "transparent"};
                padding: 14px 18px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ color: {C.TEXT_PRIMARY}; }}
        """)
    def _switch_tab(self, tab_id: str) -> None:
        self._current_tab = tab_id
        for tid, btn in self._tab_buttons.items():
            self._apply_tab_style(btn, tid == tab_id)
        self.refresh()

    def refresh(self) -> None:
        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        all_meta = self.store.list_all()
        # Sort by last_activity desc
        all_meta.sort(key=lambda m: m.get("last_activity", 0), reverse=True)
        if self._current_tab == "in_progress":
            items = [m for m in all_meta if m.get("status") == STATUS_IN_PROGRESS]
            self._render(items, empty_msg="暂无进行中的项目，点击右上角“新建项目”开始。")
        else:
            items = [m for m in all_meta if m.get("status") == STATUS_COMPLETED]
            self._render(items, empty_msg="暂无已完成的项目。")

    def _render(self, items: list, empty_msg: str) -> None:
        if not items:
            empty = QLabel(empty_msg)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 14px; padding: 60px;")
            self._grid.addWidget(empty, 0, 0)
            return
        cols = 4
        for i, m in enumerate(items):
            card = ProjectCard(m, self)
            card.clicked.connect(self.openProject.emit)
            card.openInNewWindow.connect(self.openProjectInNewWindow.emit)
            card.deleteRequested.connect(self.deleteProject.emit)
            card.renameRequested.connect(self.renameProject.emit)
            card.editRequested.connect(self.editProject.emit)
            card.markCompleted.connect(self.markProjectCompleted.emit)
            card.markInProgress.connect(self.markProjectInProgress.emit)
            card.openSourceDir.connect(self.openProjectSourceDir.emit)
            card.exportRequested.connect(self.exportProject.emit)
            card.projectSettingsRequested.connect(self.projectSettingsRequested.emit)
            card.coverRequested.connect(self.setCoverRequested.emit)
            self._grid.addWidget(card, i // cols, i % cols)
