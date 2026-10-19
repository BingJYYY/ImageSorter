"""Cover image picker dialog: choose from project's classified images or any file."""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFileDialog, QFrame, QWidget,
)

from ..core.project import Project
from ..core.thumbnail import ThumbnailCache
from .widgets.button_style import apply_gold_button
from .widgets.frameless_dialog import FramelessDialog
from . import colors as C


class CoverPickerDialog(FramelessDialog):
    def __init__(self, project: Project, thumb_cache: Optional[ThumbnailCache],
                 parent=None):
        super().__init__("选择项目封面", parent)
        self.project = project
        self.thumb_cache = thumb_cache
        self.result_path: Optional[Path] = None
        self.setMinimumSize(640, 480)
        self.resize(720, 540)
        self._build()

    def _build(self) -> None:
        root = self.body_layout
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("选择封面图")
        title.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-size: 16px; font-weight: 700;")
        root.addWidget(title)

        hint = QLabel("从项目的已分类图片里选，或从任意位置选一张。")
        hint.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 12px;")
        root.addWidget(hint)

        # Preview
        self.preview = QLabel()
        self.preview.setFixedHeight(220)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"""
            background-color: {C.BG_PANEL};
            border-radius: 10px;
            color: {C.TEXT_MUTED};
        """)
        self.preview.setText("未选择")
        root.addWidget(self.preview)

        # Two source tabs
        from PySide6.QtWidgets import QTabWidget
        tabs = QTabWidget()

        # Tab 1: from project classified
        classified_tab = QWidget()
        cl = QVBoxLayout(classified_tab)
        self.classified_list = QListWidget()
        self.classified_list.setIconSize(self.classified_list.iconSize())
        self.classified_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.classified_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.classified_list.setGridSize(self.classified_list.gridSize())
        self.classified_list.setMovement(QListWidget.Movement.Static)
        self._populate_classified()
        self.classified_list.itemClicked.connect(self._on_classified_pick)
        cl.addWidget(self.classified_list)
        tabs.addTab(classified_tab, "来自已分类图")

        # Tab 2: from anywhere
        any_tab = QWidget()
        al = QVBoxLayout(any_tab)
        any_lbl = QLabel("从任意目录选一张图作为封面。")
        any_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 12px;")
        al.addWidget(any_lbl)
        any_btn = QPushButton("浏览…")
        apply_gold_button(any_btn, compact=True)
        any_btn.clicked.connect(self._pick_any)
        al.addWidget(any_btn)
        al.addStretch(1)
        tabs.addTab(any_tab, "从任意位置")

        root.addWidget(tabs, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        clear = QPushButton("清除封面")
        clear.setProperty("accent", "danger")
        clear.clicked.connect(self._clear)
        footer.addWidget(clear)
        ok = QPushButton("设为封面")
        apply_gold_button(ok, compact=True)
        ok.clicked.connect(self._accept)
        ok.setEnabled(False)
        self._ok_btn = ok
        footer.addWidget(ok)
        root.addLayout(footer)

    def _populate_classified(self) -> None:
        """Show classified images from project history."""
        seen = set()
        items: List[Path] = []

        def add(path: Path) -> None:
            key = str(path)
            if key in seen:
                return
            seen.add(key)
            if path.exists():
                items.append(path)

        for rec in self.project.history:
            if rec.src_path:
                add(Path(rec.src_path))
        for src in self.project.classified.keys():
            add(Path(src))
        for cat in self.project.categories:
            target = Path(cat.target_dir) if cat.target_dir else None
            if target is None or not target.is_dir():
                continue
            count = 0
            for child in target.iterdir():
                if count >= 300:
                    break
                if child.is_file() and child.suffix.lower() in {
                    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
                    ".tif", ".tiff", ".avif", ".heic", ".heif",
                }:
                    add(child)
                    count += 1
        for path in self.project.file_order[:500]:
            add(Path(path))
        for p in items:
            it = QListWidgetItem(p.name)
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            pm = self._load_thumb(p, size=120)
            if pm:
                it.setIcon(pm)
            self.classified_list.addItem(it)
        if not items:
            placeholder = QListWidgetItem("暂无已分类图片")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.classified_list.addItem(placeholder)

    def _load_thumb(self, p: Path, size: int = 120) -> Optional[QPixmap]:
        try:
            if self.thumb_cache:
                tp = self.thumb_cache.get_or_generate(p)
                if tp and tp.exists():
                    pm = QPixmap(str(tp))
                    if not pm.isNull():
                        return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            # Fallback to direct loading at smaller size
            from PySide6.QtGui import QImage
            from PIL import Image, ImageOps
            from io import BytesIO
            with Image.open(str(p)) as img:
                img = ImageOps.exif_transpose(img) or img
                img.thumbnail((size * 2, size * 2))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                buf = BytesIO()
                img.save(buf, "JPEG", quality=80)
                data = buf.getvalue()
                qimg = QImage.fromData(data)
                return QPixmap.fromImage(qimg).scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
        except Exception:
            return None

    def _on_classified_pick(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.ItemDataRole.UserRole)
        if not p:
            return
        self._show_preview(Path(p))

    def _pick_any(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "选择封面图", "", "图片 (*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.heic *.heif)")
        if f:
            self._show_preview(Path(f))

    def _show_preview(self, p: Path) -> None:
        pm = self._load_thumb(p, size=400)
        if pm and not pm.isNull():
            self.preview.setPixmap(pm)
            self.preview.setText("")
            self.result_path = p
            self._ok_btn.setEnabled(True)
        else:
            self.preview.setText("无法预览")
            self.result_path = None
            self._ok_btn.setEnabled(False)

    def _clear(self) -> None:
        self.result_path = None
        self.accept()

    def _accept(self) -> None:
        if self.result_path:
            self.accept()
