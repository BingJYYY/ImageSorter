"""New project wizard: source dir + recursive choice + categories + sort + preview."""

from __future__ import annotations
import os, time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QFileDialog, QLineEdit, QCheckBox, QComboBox, QScrollArea, QRadioButton,
    QMessageBox, QGroupBox, QFormLayout,
)

from ..core.project import Project, Category, new_project_id
from ..core.image_loader import scan_directory, sort_files
from ..core.thumbnail import ThumbnailCache
from ..core.settings_store import GlobalSettings
from ..core.shortcut_conflicts import find_category_conflicts
from .widgets.category_editor import CategoryListWidget
from .widgets.button_style import apply_gold_button
from . import colors as C


SORT_FIELDS = [
    ("name", "名称"),
    ("date_taken", "拍摄日期"),
    ("modified", "修改日期"),
    ("created", "创建日期"),
    ("accessed", "访问日期"),
    ("type", "类型"),
    ("size", "大小"),
    ("resolution", "分辨率（像素总数）"),
    ("width", "宽度"),
    ("height", "高度"),
    ("ratio", "宽高比"),
    ("camera_model", "拍摄机型"),
]


class NewProjectWizard(QWidget):
    """Multi-section single-page wizard."""

    projectCreated = Signal(str)  # project id

    def __init__(self, global_settings: GlobalSettings, parent=None):
        super().__init__(parent)
        self.global_settings = global_settings
        self._category_rows: List[_CategoryEditor] = []
        self._file_list: List[Path] = []
        self._sorted_files: List[Path] = []
        self._thumb_cache: Optional[ThumbnailCache] = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 14)
        root.setSpacing(12)

        # Header
        title = QLabel("新建项目")
        title.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-size: 24px; font-weight: 700;")
        root.addWidget(title)

        sub = QLabel("选择图片源目录、分类目录与排序方式，预览满意后即可开始筛选。")
        sub.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 13px;")
        root.addWidget(sub)

        # Everything above the footer lives in a scroll area so the window can
        # be small without clipping buttons.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(14)

        # --- Source group ---
        src_box = self._make_group("图片源")
        sf = QFormLayout()
        sf.setContentsMargins(0, 0, 0, 0)
        src_row = QHBoxLayout()
        self.src_input = QLineEdit()
        self.src_input.setPlaceholderText("选择包含图片的文件夹")
        src_row.addWidget(self.src_input, 1)
        src_browse = QPushButton("浏览…")
        src_browse.clicked.connect(self._pick_source)
        src_row.addWidget(src_browse)
        self.scan_btn = QPushButton("扫描")
        apply_gold_button(self.scan_btn, compact=True)
        self.scan_btn.clicked.connect(self._scan)
        src_row.addWidget(self.scan_btn)
        self.src_count = QLabel("未扫描")
        self.src_count.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        src_row.addWidget(self.src_count)
        sf.addRow("目录:", src_row)

        self.recursive_check = QCheckBox("递归扫描所有子目录")
        self.recursive_check.setChecked(self.global_settings.get("scan_recursive", True))
        sf.addRow("", self.recursive_check)

        src_box.layout().addLayout(sf)
        content_layout.addWidget(src_box)

        # --- Categories group ---
        self.cat_box = self._make_group("分类与目标目录（点击 + 新建分类 一个一个添加）")
        cat_container = QVBoxLayout()
        cat_container.setContentsMargins(0, 4, 0, 4)
        cat_container.setSpacing(6)
        # Categories are always created manually for each project; there are
        # no global presets.
        self.cat_editor = CategoryListWidget(initial=[])
        self.cat_editor.setMinimumHeight(260)
        cat_container.addWidget(self.cat_editor, 1)
        self.cat_box.layout().addLayout(cat_container)
        content_layout.addWidget(self.cat_box)

        # --- Operation + Sort group ---
        sort_box = self._make_group("操作与排序")
        sort_form = QFormLayout()
        sort_form.setContentsMargins(0, 0, 0, 0)

        op_row = QHBoxLayout()
        self.op_copy = QRadioButton("复制")
        self.op_move = QRadioButton("移动")
        op = self.global_settings.get("operation_mode", "copy")
        self.op_copy.setChecked(op == "copy")
        self.op_move.setChecked(op == "move")
        op_row.addWidget(self.op_copy)
        op_row.addWidget(self.op_move)
        op_row.addStretch(1)
        sort_form.addRow("默认操作:", op_row)

        sf_row = QHBoxLayout()
        self.sort_field = QComboBox()
        for k, v in SORT_FIELDS:
            self.sort_field.addItem(v, k)
        idx = self.sort_field.findData(self.global_settings.get("default_sort_field", "name"))
        if idx >= 0:
            self.sort_field.setCurrentIndex(idx)
        self.sort_field.currentIndexChanged.connect(self._refresh_preview)
        sf_row.addWidget(self.sort_field, 1)
        self.sort_desc = QCheckBox("降序")
        self.sort_desc.setChecked(self.global_settings.get("default_sort_descending", False))
        self.sort_desc.stateChanged.connect(self._refresh_preview)
        sf_row.addWidget(self.sort_desc)
        sort_form.addRow("排序方式:", sf_row)

        sort_box.layout().addLayout(sort_form)
        content_layout.addWidget(sort_box)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)



        # --- Footer (always visible) ---
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("项目名称（可选，留空用源目录名）")
        self.name_input.setMaximumWidth(300)
        footer.addWidget(self.name_input)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(lambda: self.projectCreated.emit(""))
        footer.addWidget(cancel_btn)
        self.start_btn = QPushButton("创建并开始筛选 →")
        apply_gold_button(self.start_btn)
        self.start_btn.clicked.connect(self._on_create)
        footer.addWidget(self.start_btn)
        root.addLayout(footer)

    def _make_group(self, title: str) -> QGroupBox:
        gb = QGroupBox(title)
        gb.setStyleSheet(f"""
            QGroupBox {{
                background-color: {C.BG_BASE};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
                margin-top: 16px;
                padding: 16px;
                color: {C.TEXT_SECONDARY};
                font-size: 13px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 6px;
                color: {C.ACCENT_GOLD};
            }}
        """)
        l = QVBoxLayout(gb)
        l.setContentsMargins(16, 16, 16, 16)
        return gb

    def _build_category_rows(self) -> None:
        # Legacy: kept as a no-op so the wizard's UI continues to work after
        # the v1.0.1 refactor (rows are now driven by CategoryListWidget).
        return

    def _pick_source(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择图片源目录")
        if d:
            self.src_input.setText(d)

    def _scan(self) -> None:
        d = self.src_input.text().strip()
        if not d:
            QMessageBox.warning(self, "未选择目录", "请先选择图片源目录。")
            return
        p = Path(d)
        if not p.exists():
            QMessageBox.warning(self, "目录不存在", f"找不到：{d}")
            return
        self.src_count.setText("扫描中…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        rec = self.recursive_check.isChecked()
        self._file_list = scan_directory(p, recursive=rec)
        self.src_count.setText(f"共 {len(self._file_list)} 张图片")
        # Initialize thumbnail cache next to source
        # Thumbnail cache is initialised lazily by the filter view; the wizard
        # itself no longer previews thumbnails in v1.0.1.
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        # Preview grid removed in v1.0.1; starting position is now picked in the
        # filter view via the "预览" button.
        if not self._file_list:
            self._sorted_files = []
            return
        field = self.sort_field.currentData()
        desc = self.sort_desc.isChecked()
        self._sorted_files = sort_files(self._file_list, field, desc)

    def _on_create(self) -> None:
        if not self._sorted_files:
            QMessageBox.warning(self, "未扫描", "请先扫描源目录。")
            return
        src_dir = self.src_input.text().strip()
        name = self.name_input.text().strip() or Path(src_dir).name or "未命名项目"
        cats: List[Category] = self.cat_editor.collect()
        conflicts = find_category_conflicts(
            cats,
            self.global_settings.all(),
            self.global_settings.get("multi_category_modifier", "Ctrl"),
        )
        if conflicts:
            QMessageBox.warning(
                self,
                "快捷键冲突",
                "请先修正以下分类快捷键：\n\n" + "\n".join(conflicts),
            )
            return
        if not cats:
            reply = QMessageBox.question(
                self, "未配置分类",
                "你还没为任何分类配置目标目录。继续创建项目吗？（之后可以在项目设置里添加）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        op_mode = "move" if self.op_move.isChecked() else "copy"
        rec = self.recursive_check.isChecked()
        now = time.time()
        proj = Project(
            id=new_project_id(),
            name=name,
            source_dir=src_dir,
            recursive=rec,
            operation_mode=op_mode,
            sort_field=self.sort_field.currentData(),
            sort_descending=self.sort_desc.isChecked(),
            categories=cats,
            created_at=now,
            updated_at=now,
            status="in_progress",
            cover_image=None,
            file_order=[str(p) for p in self._sorted_files],
            current_index=-1,
            classified={},
            history=[],
            last_activity=now,
        )
        self.projectCreated.emit(proj.id)
        # Caller will handle persistence; we pass back data via callback mechanism below
        self._pending_project = proj

    def take_pending_project(self) -> Optional[Project]:
        return getattr(self, "_pending_project", None)

