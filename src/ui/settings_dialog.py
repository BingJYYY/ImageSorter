"""Settings dialog: global defaults + per-project overrides (when project given)."""

from __future__ import annotations
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QFormLayout, QComboBox, QSpinBox, QCheckBox, QSlider, QLineEdit,
    QTabWidget, QWidget, QColorDialog, QMessageBox, QScrollArea, QGroupBox,
    QFileDialog, QRadioButton, QButtonGroup,
)

from ..core.settings_store import GlobalSettings, ProjectSettingsStore, DEFAULTS
from ..core.project import Project, ProjectStore
from ..core.shortcut_conflicts import find_category_conflicts
from .widgets.key_capture import KeyCaptureButton
from .widgets.category_editor import CategoryListWidget
from .widgets.button_style import apply_gold_button, apply_icon_button
from .widgets.frameless_dialog import FramelessDialog
from .cover_picker import CoverPickerDialog
from . import colors as C


_MISSING = object()


class _KeyRow(QWidget):
    def __init__(self, label: str, value: str, on_change: Callable[[str], None],
                 placeholder: str = "点击录制", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        layout.addWidget(lbl, 1)
        self.btn = KeyCaptureButton(initial=value, placeholder=placeholder)
        self.btn.keyChanged.connect(on_change)
        layout.addWidget(self.btn)
        # Small clear button (X) to unbind the shortcut.
        self.clear_btn = QPushButton("✕")
        apply_icon_button(self.clear_btn, 28)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("清除绑定（双击或按 Backspace 也可）")
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_btn)

    def _on_clear(self) -> None:
        self.btn.clear()


class SettingsDialog(FramelessDialog):
    settingsChanged = Signal()

    def __init__(self, global_settings: GlobalSettings,
                 project_settings: Optional[ProjectSettingsStore] = None,
                 project: Optional[Project] = None,
                 project_store: Optional[ProjectStore] = None,
                 thumb_cache=None,
                 parent=None):
        title = "项目设置" if project_settings is not None else "设置"
        super().__init__(title, parent)
        self.setMinimumSize(820, 640)
        self.gs = global_settings
        self.ps = project_settings
        self.project = project
        self.project_store = project_store
        self.thumb_cache = thumb_cache
        self.applied = False
        self._dirty: set[str] = set()
        self._draft = (
            self.ps.merged() if self.ps is not None else self.gs.all()
        )
        self._build()

    def _build(self) -> None:
        root = self.body_layout

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "通用")
        tabs.addTab(self._tab_appearance(), "外观")
        tabs.addTab(self._tab_filter(), "筛选")
        tabs.addTab(self._tab_keys(), "按键")
        if self.ps is not None:
            tabs.addTab(self._tab_categories(), "分类")
        if self.project is not None:
            tabs.addTab(self._tab_cover(), "项目封面")
        tabs.addTab(self._tab_exif(), "EXIF 信息条")
        tabs.addTab(self._tab_thumb(), "缩略图缓存")
        root.addWidget(tabs, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 12, 20, 16)
        if self.ps is not None:
            scope_lbl = QLabel("全局默认 + 当前项目覆盖")
        else:
            scope_lbl = QLabel("全局默认")
        scope_lbl.setStyleSheet(f"color: {C.ACCENT_GOLD if self.ps else C.TEXT_SECONDARY}; font-size: 12px;")
        footer.addWidget(scope_lbl)
        if self.ps is not None:
            reset_proj = QPushButton("重置项目为全局默认")
            reset_proj.setProperty("accent", "danger")
            reset_proj.clicked.connect(self._reset_project)
            footer.addWidget(reset_proj)
        footer.addStretch(1)
        cancel = QPushButton("关闭")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        apply_btn = QPushButton("应用")
        apply_btn.setMinimumWidth(96)
        apply_gold_button(apply_btn)
        apply_btn.clicked.connect(self._save)
        footer.addWidget(apply_btn)
        wrap = QWidget()
        wrap.setStyleSheet(f"background-color: {C.BG_PANEL}; border-top: 1px solid {C.DIVIDER};")
        wrap.setLayout(footer)
        root.addWidget(wrap)


    # ---- Radio change handlers ----
    def _on_backup_changed(self, btn, checked):
        if not checked:
            return
        for value, rb in self._backup_radios.items():
            if rb is btn:
                self._set_global("backup_format", value)
                return

    def _on_op_changed(self, btn, checked):
        if not checked:
            return
        for value, rb in self._op_radios.items():
            if rb is btn:
                self._set_global("operation_mode", value)
                return

    def _tab_categories(self) -> QWidget:
        """Per-project categories tab. Shown only when project_settings is provided."""
        w = QScrollArea()
        inner = QWidget()
        f = QVBoxLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)
        f.setSpacing(12)
        intro = QLabel(
            "为当前项目添加/删除分类。点击 + 新建分类 一个一个添加，\n"
            "删除分类时项目里已经分类到此文件夹的图片不会被移动（文件夹物理保留）。"
        )
        intro.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 12px;")
        intro.setWordWrap(True)
        f.addWidget(intro)
        initial_cats = list(self.project.categories) if self.project else []
        self._cat_editor_project = CategoryListWidget(initial=initial_cats)
        f.addWidget(self._cat_editor_project, 1)
        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_cover(self) -> QWidget:
        w = QWidget()
        f = QVBoxLayout(w)
        f.setContentsMargins(20, 20, 20, 20)
        f.setSpacing(12)

        hint = QLabel("封面会显示在任务列表的项目卡片上。")
        hint.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 12px;")
        f.addWidget(hint)

        self._cover_preview = QLabel()
        self._cover_preview.setMinimumHeight(280)
        self._cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_preview.setStyleSheet(
            f"background-color: {C.BG_PANEL}; border: 1px solid {C.BORDER};"
            "border-radius: 10px;"
        )
        self._refresh_cover_preview()
        f.addWidget(self._cover_preview, 1)

        row = QHBoxLayout()
        choose = QPushButton("选择封面…")
        apply_gold_button(choose, compact=True)
        choose.clicked.connect(self._choose_cover)
        row.addWidget(choose)
        clear = QPushButton("清除封面")
        clear.setProperty("accent", "danger")
        clear.clicked.connect(self._clear_cover)
        row.addWidget(clear)
        row.addStretch(1)
        f.addLayout(row)
        return w

    def _refresh_cover_preview(self) -> None:
        if not hasattr(self, "_cover_preview"):
            return
        from PySide6.QtGui import QPixmap
        path = self.project.cover_image if self.project else None
        if path:
            from pathlib import Path
            p = Path(path)
            if p.exists():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    self._cover_preview.setPixmap(
                        pm.scaled(
                            720, 280,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    self._cover_preview.setText("")
                    return
        self._cover_preview.setPixmap(QPixmap())
        self._cover_preview.setText("尚未设置封面")
        self._cover_preview.setStyleSheet(
            f"background-color: {C.BG_PANEL}; border: 1px solid {C.BORDER};"
            f"border-radius: 10px; color: {C.TEXT_MUTED};"
        )

    def _choose_cover(self) -> None:
        if self.project is None:
            return
        dlg = CoverPickerDialog(self.project, self.thumb_cache, self)
        if dlg.exec():
            self._persist_project(
                cover_image=str(dlg.result_path) if dlg.result_path else None
            )
            self._refresh_cover_preview()

    def _clear_cover(self) -> None:
        if self.project is None:
            return
        self._persist_project(cover_image=None)
        self._refresh_cover_preview()

    def _persist_project(self, categories=None, cover_image=...):
        """Save only the changed project fields onto the latest project state."""
        if self.project is None or self.project_store is None:
            return
        latest = self.project_store.load_project(self.project.id) or self.project
        if categories is not None:
            latest.categories = categories
        if cover_image is not ...:
            latest.cover_image = cover_image
        self.project_store.save_project(latest)
        self.project = latest

    # ---- Tabs ----
    def _tab_general(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)
        self.startup_mode = QComboBox()
        self.startup_mode.addItem("进入任务列表", "task_list")
        self.startup_mode.addItem("自动恢复上次任务", "auto_resume")
        self._bind_combo(self.startup_mode, "startup_mode")
        f.addRow("启动行为:", self.startup_mode)

        self.raw_load_mode = QComboBox()
        self.raw_load_mode.addItem("按需加载（默认）", "on_demand")
        self.raw_load_mode.addItem("启动时加载", "on_startup")
        self._bind_combo(self.raw_load_mode, "raw_load_mode")
        f.addRow("RAW 解码库加载:", self.raw_load_mode)

        self.scan_recursive = QCheckBox("递归扫描源目录子文件夹")
        self._bind_check(self.scan_recursive, "scan_recursive")
        f.addRow("", self.scan_recursive)

        self.use_md5 = QCheckBox("同名冲突时启用 MD5 内容比对")
        self._bind_check(self.use_md5, "use_md5_dedup")
        f.addRow("", self.use_md5)

        self.dup_strategy = QComboBox()
        self.dup_strategy.addItem("自动重命名 xxx (1).jpg", "rename")
        self.dup_strategy.addItem("跳过", "skip")
        self.dup_strategy.addItem("覆盖", "overwrite")
        self._bind_combo(self.dup_strategy, "duplicate_strategy")
        f.addRow("同名冲突默认策略:", self.dup_strategy)

        # 导出/备份默认格式: 三个 radio (仅 ZIP / 仅文件夹 / ZIP + 文件夹 双份)
        self._backup_group = QButtonGroup(self)
        self._backup_radios = {}
        backup_row = QHBoxLayout()
        for label, value in [
            ("仅 ZIP (单文件)", "zip"),
            ("仅文件夹 (直接拷贝)", "folder"),
            ("ZIP + 文件夹 (双份冗余)", "both"),
        ]:
            rb = QRadioButton(label)
            self._backup_group.addButton(rb)
            self._backup_radios[value] = rb
            backup_row.addWidget(rb)
        backup_row.addStretch(1)
        current_backup = self._get("backup_format", "zip")
        self._backup_radios.get(current_backup, list(self._backup_radios.values())[0]).setChecked(True)
        f.addRow("导出/备份默认格式:", backup_row)
        # Track current value via the group's buttonToggled signal.
        self._backup_group.buttonToggled.connect(self._on_backup_changed)
        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_appearance(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)

        # Gold accent
        self.gold_input = QLineEdit(self._get("theme_accent_gold", C.ACCENT_GOLD))
        self.gold_input.setMaximumWidth(140)
        gold_btn = QPushButton("选…")
        gold_btn.clicked.connect(lambda: self._pick_color(self.gold_input))
        gold_row = QHBoxLayout()
        gold_row.addWidget(self.gold_input)
        gold_row.addWidget(gold_btn)
        f.addRow("主金高亮:", gold_row)

        self.rust_input = QLineEdit(self._get("theme_accent_rust", C.ACCENT_RUST))
        self.rust_input.setMaximumWidth(140)
        rust_btn = QPushButton("选…")
        rust_btn.clicked.connect(lambda: self._pick_color(self.rust_input))
        rust_row = QHBoxLayout()
        rust_row.addWidget(self.rust_input)
        rust_row.addWidget(rust_btn)
        f.addRow("副红高亮:", rust_row)

        self.font_size = QSpinBox()
        self.font_size.setRange(10, 28)
        self.font_size.setValue(int(self._get("font_size", 14)))
        f.addRow("字体大小:", self.font_size)

        self.bg_blur = QSlider(Qt.Orientation.Horizontal)
        self.bg_blur.setRange(0, 20)
        self.bg_blur.setValue(int(self._get("background_blur", 0)))
        f.addRow("背景模糊 (0=关):", self.bg_blur)

        self.bg_transparency = QSlider(Qt.Orientation.Horizontal)
        self.bg_transparency.setRange(40, 100)
        self.bg_transparency.setValue(int(self._get("background_transparency", 100)))
        f.addRow("背景不透明度:", self.bg_transparency)

        hint = QLabel("修改主色后请重启软件生效；字体/模糊实时生效。")
        hint.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px;")
        f.addRow("", hint)
        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_filter(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)

        self._op_group = QButtonGroup(self)
        self._op_radios = {}
        op_row = QHBoxLayout()
        for label, value in [("复制", "copy"), ("移动", "move")]:
            rb = QRadioButton(label)
            self._op_group.addButton(rb)
            self._op_radios[value] = rb
            op_row.addWidget(rb)
        op_row.addStretch(1)
        current_op = self._get("operation_mode", "copy")
        self._op_radios.get(current_op, list(self._op_radios.values())[0]).setChecked(True)
        f.addRow("默认操作:", op_row)
        self._op_group.buttonToggled.connect(self._on_op_changed)

        self.advance = QCheckBox("操作后自动跳到下一张")
        self._bind_check(self.advance, "auto_advance")
        f.addRow("", self.advance)

        self.advance_delay = QSpinBox()
        self.advance_delay.setRange(0, 5000)
        self.advance_delay.setSingleStep(50)
        self.advance_delay.setValue(int(self._get("auto_advance_delay_ms", 0)))
        f.addRow("自动跳转延时 (ms):", self.advance_delay)

        self.undo_depth = QSpinBox()
        self.undo_depth.setRange(1, 10000)
        self.undo_depth.setValue(int(self._get("undo_stack_depth", 100)))
        f.addRow("撤销栈深度:", self.undo_depth)

        self.cat_mod = QComboBox()
        self.cat_mod.addItem("Ctrl (默认)", "Ctrl")
        self.cat_mod.addItem("Shift", "Shift")
        self.cat_mod.addItem("Alt", "Alt")
        self._bind_combo(self.cat_mod, "multi_category_modifier")
        f.addRow("多分类触发修饰键:", self.cat_mod)

        self.invert_adv = QCheckBox("修饰键按下时保持当前图不切换")
        self._bind_check(self.invert_adv, "modifier_invert_advance")
        f.addRow("", self.invert_adv)

        self.wheel_action = QComboBox()
        self.wheel_action.addItem("缩放（默认）", "zoom")
        self.wheel_action.addItem("切换图片", "switch_image")
        self._bind_combo(self.wheel_action, "wheel_action")
        f.addRow("鼠标滚轮默认:", self.wheel_action)

        self.wheel_mod = QComboBox()
        self.wheel_mod.addItem("Ctrl", "Ctrl")
        self.wheel_mod.addItem("Shift", "Shift")
        self.wheel_mod.addItem("Alt", "Alt")
        self._bind_combo(self.wheel_mod, "wheel_modifier_for_alt")
        f.addRow("滚轮切换图片时启用缩放需按住的键:", self.wheel_mod)

        self.permanent_delete = QCheckBox("Delete 永久删除（不可撤销）")
        self._bind_check(self.permanent_delete, "permanent_delete")
        f.addRow("", self.permanent_delete)

        self.start_logic = QComboBox()
        self.start_logic.addItem("线性（从选中处到末尾后结束）", "linear")
        self.start_logic.addItem("循环（末尾后回到第一张直到全部）", "wrap")
        self._bind_combo(self.start_logic, "start_logic")
        f.addRow("起始位置筛选逻辑:", self.start_logic)


        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_keys(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)

        from ..core.settings_store import DEFAULTS as D
        # ---- 系统动作按键 ----
        sys_grp = QGroupBox("系统动作按键")
        sys_grp.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {C.BORDER}; border-radius: 8px; margin-top: 12px; padding-top: 12px; color: {C.TEXT_SECONDARY}; font-weight: 600; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {C.ACCENT_GOLD}; }}"
        )
        sys_form = QFormLayout(sys_grp)
        sys_form.setContentsMargins(16, 16, 16, 16)
        self._key_widgets = []
        for label, key in [
            ("下一张", "next_image_key"),
            ("上一张", "prev_image_key"),
            ("下一张 (备用)", "next_image_alt_key"),
            ("上一张 (备用)", "prev_image_alt_key"),
            ("第一张", "first_image_key"),
            ("最后一张", "last_image_key"),
            ("返回任务列表", "back_to_grid_key"),
            ("切换全屏", "fullscreen_key"),
            ("撤销", "undo_key"),
            ("放大", "zoom_in_key"),
            ("缩小", "zoom_out_key"),
            ("缩放重置", "zoom_reset_key"),
            ("删除", "delete_key"),
            ("预览", "preview_key"),
        ]:
            initial = self._get(key, D.get(key, ""))
            placeholder = "未绑定" if key in ("first_image_key", "last_image_key") else "点击录制"
            row = _KeyRow(label, initial,
                          lambda v, k=key: self._set_global(k, v),
                          placeholder=placeholder)
            sys_form.addRow(row)
            self._key_widgets.append((key, row))
        f.addRow(sys_grp)

        note = QLabel(
            "系统按键支持任意组合（含修饰键）。双击按键框或点右侧 × 可解绑。"
            "分类快捷键在项目的「分类」标签页里设置。"
        )
        note.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 11px;")
        note.setWordWrap(True)
        f.addRow("", note)
        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_exif(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)

        self.exif_visible = QCheckBox("在底部显示 EXIF 信息条")
        self._bind_check(self.exif_visible, "exif_bar_visible")
        f.addRow("", self.exif_visible)

        from ..core.exif_format import EXIF_FIELDS
        self._exif_field_checks = {}
        for key, label in EXIF_FIELDS:
            cb = QCheckBox(label)
            cb.setChecked(bool(self._get(f"exif_fields.{key}", True)))
            self._exif_field_checks[key] = cb
            f.addRow("", cb)
        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    def _tab_thumb(self) -> QWidget:
        w = QScrollArea()
        inner = QWidget()
        f = QFormLayout(inner)
        f.setContentsMargins(20, 20, 20, 20)

        self.thumb_max_bytes = QSpinBox()
        self.thumb_max_bytes.setRange(0, 100000)
        self.thumb_max_bytes.setSingleStep(100)
        self.thumb_max_bytes.setSuffix(" MB")
        v = int(self._get("thumb_cache_max_bytes", 0) / (1024 * 1024)) if self._get("thumb_cache_max_bytes", 0) else 0
        self.thumb_max_bytes.setValue(v)
        f.addRow("单项目缓存上限 (0=不限):", self.thumb_max_bytes)

        self.thumb_per_img = QSpinBox()
        self.thumb_per_img.setRange(8, 2048)
        self.thumb_per_img.setSingleStep(8)
        self.thumb_per_img.setSuffix(" KB")
        self.thumb_per_img.setValue(int(self._get("thumb_max_per_image_bytes", 200 * 1024) / 1024))
        f.addRow("单张缩略图上限:", self.thumb_per_img)

        self.thumb_dim = QSpinBox()
        self.thumb_dim.setRange(96, 1920)
        self.thumb_dim.setSingleStep(32)
        self.thumb_dim.setSuffix(" px")
        self.thumb_dim.setValue(int(self._get("thumb_max_dimension", 480)))
        f.addRow("缩略图最长边:", self.thumb_dim)

        clear_btn = QPushButton("清空当前项目缓存（需打开项目后生效）")
        clear_btn.setProperty("accent", "danger")
        clear_btn.clicked.connect(self._clear_current_thumb_cache)
        f.addRow("", clear_btn)

        w.setWidget(inner)
        w.setWidgetResizable(True)
        return w

    # ---- Helpers ----
    def _pick_color(self, line_edit: QLineEdit) -> None:
        c = QColorDialog.getColor(QColor(line_edit.text() or C.ACCENT_GOLD), self)
        if c.isValid():
            line_edit.setText(c.name())

    def _bind_combo(self, combo: QComboBox, key: str) -> None:
        idx = combo.findData(self._get(key, ""))
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(
            lambda i, c=combo, k=key: self._set_global(k, c.currentData())
        )

    def _bind_check(self, cb: QCheckBox, key: str) -> None:
        cb.setChecked(bool(self._get(key, False)))
        cb.stateChanged.connect(lambda v, k=key: self._set_global(k, bool(v)))

    def _get(self, key: str, default=None):
        cur = self._draft
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def _set_global(self, key: str, value) -> None:
        old = self._get(key, _MISSING)
        if old is not _MISSING and old == value:
            return
        parts = key.split(".")
        cur = self._draft
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value
        self._dirty.add(key)

    def _clear_current_thumb_cache(self) -> None:
        if self.thumb_cache is None:
            QMessageBox.information(
                self, "清空缓存",
                "请先从项目里打开设置，或打开一次项目以初始化缓存。",
            )
            return
        removed = self.thumb_cache.clear_all()
        QMessageBox.information(
            self, "清空缓存", f"已删除 {removed} 个缩略图缓存文件。"
        )

    def _reset_project(self) -> None:
        if self.ps is None:
            return
        self.ps.reset_to_global()
        self.ps.save()
        self._draft = self.ps.merged()
        self._dirty.clear()
        QMessageBox.information(
            self, "已重置",
            "项目设置已重置为全局默认。",
        )
        self.settingsChanged.emit()
        self.accept()

    def _save(self) -> None:
        # Persist non-bound settings (as project overrides in project mode).
        self._set_global("theme_accent_gold", self.gold_input.text() or C.ACCENT_GOLD)
        self._set_global("theme_accent_rust", self.rust_input.text() or C.ACCENT_RUST)
        self._set_global("font_size", int(self.font_size.value()))
        self._set_global("background_blur", int(self.bg_blur.value()))
        self._set_global("background_transparency", int(self.bg_transparency.value()))
        self._set_global("auto_advance", bool(self.advance.isChecked()))
        self._set_global("auto_advance_delay_ms", int(self.advance_delay.value()))
        self._set_global("undo_stack_depth", int(self.undo_depth.value()))
        self._set_global("exif_bar_visible", bool(self.exif_visible.isChecked()))
        for key, cb in self._exif_field_checks.items():
            self._set_global(f"exif_fields.{key}", bool(cb.isChecked()))
        self._set_global("thumb_cache_max_bytes", int(self.thumb_max_bytes.value()) * 1024 * 1024)
        self._set_global("thumb_max_per_image_bytes", int(self.thumb_per_img.value()) * 1024)
        self._set_global("thumb_max_dimension", int(self.thumb_dim.value()))
        # Keys
        for key, row in self._key_widgets:
            self._set_global(key, row.btn.value())

        if hasattr(self, "_cat_editor_project") and self.project is not None:
            cats = self._cat_editor_project.collect()
            effective = self._draft
            conflicts = find_category_conflicts(
                cats,
                effective,
                effective.get("multi_category_modifier", "Ctrl"),
            )
            if conflicts:
                QMessageBox.warning(
                    self,
                    "快捷键冲突",
                    "请先修正以下分类快捷键：\n\n" + "\n".join(conflicts),
                )
                return
            self._persist_project(categories=cats)
        elif self.project_store is not None and (
            self._dirty
            & {
                "next_image_key", "prev_image_key", "next_image_alt_key",
                "prev_image_alt_key", "first_image_key", "last_image_key",
                "back_to_grid_key", "fullscreen_key", "undo_key",
                "delete_key", "zoom_in_key", "zoom_out_key",
                "zoom_reset_key", "preview_key",
            }
        ):
            # Global settings affect every project, so check their category
            # hotkeys as well before accepting the new shortcuts.
            effective = self._draft
            project_conflicts = []
            for meta in self.project_store.list_all():
                project = self.project_store.load_project(meta.get("id", ""))
                if project is None:
                    continue
                for message in find_category_conflicts(
                    project.categories,
                    effective,
                    effective.get("multi_category_modifier", "Ctrl"),
                ):
                    project_conflicts.append(f"项目「{project.name}」：{message}")
            if project_conflicts:
                QMessageBox.warning(
                    self,
                    "快捷键冲突",
                    "以下项目的分类快捷键与新设置冲突：\n\n"
                    + "\n".join(project_conflicts),
                )
                return

        # Commit the draft only now.  Closing the dialog never mutates the
        # live global/project settings.
        for key in sorted(self._dirty):
            value = self._get(key)
            if self.ps is not None:
                if value == self.gs.get(key):
                    self.ps.clear_override(key)
                else:
                    self.ps.set_override(key, value)
            else:
                self.gs.set(key, value)

        if self.ps is not None:
            self.ps.save()
        else:
            self.gs.save()
        self.applied = True
        self.settingsChanged.emit()
        self.accept()
