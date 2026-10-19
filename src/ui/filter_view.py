"""Main filter view: single image at a time, with progress, EXIF bar, shortcuts."""

from __future__ import annotations
import time
from pathlib import Path
from typing import Optional, List, Dict

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QColor, QKeyEvent, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QProgressBar, QMessageBox, QApplication, QScrollArea,
)

from ..core.project import Project, Category, OperationRecord
from ..core.image_loader import metadata_for, open_for_display
from ..core.thumbnail import ThumbnailCache
from ..core.ops import (
    copy_file, move_file, delete_permanently, unique_dest_path,
    move_to_app_trash,
)
from ..core.undo import UndoStack
from ..core.exif_format import EXIF_FIELDS, format_exif
from ..core.csv_log import CsvLogger
from ..core.settings_store import ProjectSettingsStore
from .widgets.image_view import ImageView
from .widgets.key_match import event_matches
from .widgets.preview_dialog import PreviewDialog, CategoryPanel
from .widgets.button_style import apply_gold_button
from . import colors as C


class FilterView(QWidget):
    """The heart of the app: one image at a time, hotkeys drive operations."""

    closed = Signal()

    def hideEvent(self, e):
        # Close floating panel when leaving the filter view.
        panel = getattr(self, "_cats_panel", None)
        if panel is not None:
            try:
                panel.close()
            except RuntimeError:
                pass
            self._cats_panel = None
        super().hideEvent(e)
    rawLibraryLoadStarted = Signal()
    rawLibraryLoadFinished = Signal(bool)
    saveProgressRequested = Signal()
    completeChanged = Signal()
    coverRequested = Signal()
    coverCleared = Signal()
    projectSettingsRequested = Signal()
    openLogRequested = Signal()
    wheelSwitchRequested = Signal(int)  # -1 or +1

    def __init__(self, project: Project, settings: ProjectSettingsStore,
                 thumb_cache: ThumbnailCache, csv_logger: Optional[CsvLogger] = None,
                 trash_root=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.settings = settings
        self.thumb_cache = thumb_cache
        self._trash_root = (
            Path(trash_root) if trash_root is not None
            else Path(project.source_dir) / ".imgfilter_trash"
        )
        self.csv_logger = csv_logger or CsvLogger(
            project.source_dir and Path(project.source_dir).parent / ".thumbcache" / project.id / "log.csv"
            or Path("log.csv")
        )
        self._meta_cache: Dict[str, dict] = {}
        self._undo_stack = UndoStack(capacity=settings.get("undo_stack_depth", 100))
        self._building = True
        self._build()
        self._building = False
        if self.project.file_order:
            self.project.current_index = max(self.project.current_index, 0)
            self._show_current()
        # Wire wheel from image view
        self.image_view.wheelSwitchRequested.connect(self._on_wheel_switch)
        # First entry -> show preview dialog so user can pick a starting point.
        self._maybe_show_initial_preview()

    # =========================================================
    # UI construction
    # =========================================================
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ----- Top bar -----
        top = QFrame()
        top.setFixedHeight(60)
        top.setStyleSheet(f"background-color: {C.BG_PANEL}; border-bottom: 1px solid {C.DIVIDER};")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 0, 20, 0)
        back = QPushButton("← 返回任务列表")
        back.setProperty("accent", "ghost")
        back.clicked.connect(self.closed.emit)
        tl.addWidget(back)
        tl.addSpacing(8)
        title = QLabel(self.project.name)
        title.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-weight: 700; font-size: 16px;")
        tl.addWidget(title)
        tl.addStretch(1)
        # Progress count
        self.progress_label = QLabel()
        self.progress_label.setStyleSheet(f"color: {C.ACCENT_GOLD}; font-size: 16px; font-weight: 600;")
        tl.addWidget(self.progress_label)
        tl.addSpacing(20)
        op_mode = self.settings.get("operation_mode", "copy")
        self._op_badge = QLabel("复制" if op_mode == "copy" else "移动")
        self._op_badge.setStyleSheet(f"""
            color: {C.BG_BASE};
            background-color: {C.ACCENT_RUST};
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 12px;
        """)
        tl.addWidget(self._op_badge)
        tl.addSpacing(8)
        self._menu_btn = QPushButton("………")
        self._menu_btn.setProperty("accent", "ghost")
        self._menu_btn.setFixedSize(40, 32)
        self._menu_btn.clicked.connect(self._show_project_menu)
        tl.addWidget(self._menu_btn)

        # Toolbar separator
        tl.addSpacing(6)
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"color: {C.DIVIDER};")
        sep1.setFixedHeight(22)
        tl.addWidget(sep1)
        tl.addSpacing(6)

        # 预览 (preview / starting position) button
        self._preview_btn = QPushButton("▦  预览")
        self._preview_btn.setProperty("accent", "ghost")
        self._preview_btn.setToolTip("选择起始图片（空格键）")
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.clicked.connect(self._show_preview_dialog)
        tl.addWidget(self._preview_btn)

        # 分类 panel toggle
        self._cats_btn = QPushButton("☰  分类")
        self._cats_btn.setProperty("accent", "ghost")
        self._cats_btn.setToolTip("显示分类和对应的快捷键")
        self._cats_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cats_btn.setCheckable(True)
        self._cats_btn.clicked.connect(self._toggle_category_panel)
        tl.addWidget(self._cats_btn)

        root.addWidget(top)

        # ----- Center: image view -----
        self.image_view = ImageView(self)
        self.image_view.rawLoadingRequested.connect(self._on_raw_loading)
        self.image_view.rawLoadFinished.connect(self._on_raw_loaded)
        root.addWidget(self.image_view, 1)

        # ----- EXIF info bar -----
        self.exif_bar = QFrame()
        self.exif_bar.setFixedHeight(40)
        self.exif_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {C.BG_PANEL};
                border-top: 1px solid {C.DIVIDER};
            }}
            QLabel {{
                color: {C.TEXT_SECONDARY};
                font-size: 12px;
                padding: 0 12px;
            }}
        """)
        el = QHBoxLayout(self.exif_bar)
        el.setContentsMargins(0, 0, 0, 0)
        el.addStretch(1)
        self._exif_labels: Dict[str, QLabel] = {}
        for key, label in EXIF_FIELDS:
            visible = self.settings.get(f"exif_fields.{key}", True)
            lbl = QLabel(f"{label}: —")
            lbl.setVisible(visible)
            self._exif_labels[key] = lbl
            el.addWidget(lbl)
        el.addStretch(1)
        exif_visible = self.settings.get("exif_bar_visible", True)
        self.exif_bar.setVisible(exif_visible)
        root.addWidget(self.exif_bar)

        # ----- Bottom: category quick-buttons + status -----
        bottom = QFrame()
        bottom.setFixedHeight(80)
        bottom.setStyleSheet(f"background-color: {C.BG_PANEL}; border-top: 1px solid {C.DIVIDER};")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(20, 4, 20, 4)
        bl.setSpacing(2)

        status_row = QHBoxLayout()
        status_row.setSpacing(0)
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 12px;")
        status_row.addWidget(self._status_label)
        status_row.addStretch(1)
        self._autosave_label = QLabel("进度自动保存")
        self._autosave_label.setStyleSheet(
            f"color: {C.TEXT_MUTED}; font-size: 11px;"
        )
        status_row.addWidget(self._autosave_label)
        bl.addLayout(status_row)

        # Categories strip (scrollable)
        cat_scroll = QScrollArea()
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setFixedHeight(40)
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cat_scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: 0; }}")
        cat_inner = QWidget()
        cat_inner.setStyleSheet("background: transparent;")
        self._cat_strip_layout = QHBoxLayout(cat_inner)
        self._cat_strip_layout.setContentsMargins(0, 0, 0, 0)
        self._cat_strip_layout.setSpacing(6)
        self._cat_strip_layout.addStretch(1)
        self._rebuild_category_strip()
        cat_scroll.setWidget(cat_inner)
        bl.addWidget(cat_scroll)

        root.addWidget(bottom)
        self._refresh_status_label()

        # Done overlay
        self._done_overlay = QFrame(self)
        self._done_overlay.setStyleSheet(f"background-color: rgba(12, 10, 8, 230);")
        self._done_overlay.hide()
        dl = QVBoxLayout(self._done_overlay)
        dl.setContentsMargins(40, 40, 40, 40)
        dl.setSpacing(12)
        dl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_title = QLabel("全部完成！")
        self._done_title.setStyleSheet(f"color: {C.ACCENT_GOLD}; font-size: 36px; font-weight: 700;")
        self._done_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self._done_title)
        self._done_subtitle = QLabel("")
        self._done_subtitle.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-size: 16px;")
        self._done_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_subtitle.setWordWrap(True)
        dl.addWidget(self._done_subtitle)
        stats_row = QHBoxLayout()
        stats_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._done_stats_label = QLabel("")
        self._done_stats_label.setStyleSheet(f"color: {C.TEXT_SECONDARY}; font-size: 13px;")
        self._done_stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl.addWidget(self._done_stats_label)
        dl.addStretch(1)
        done_btns = QHBoxLayout()
        done_btns.setSpacing(12)
        done_btns.setAlignment(Qt.AlignmentFlag.AlignCenter)
        back_btn = QPushButton("返回任务列表")
        apply_gold_button(back_btn, compact=True)
        back_btn.clicked.connect(self.closed.emit)
        done_btns.addWidget(back_btn)
        continue_btn = QPushButton("继续查看（可以撤销）")
        continue_btn.setProperty("accent", "ghost")
        continue_btn.clicked.connect(self._hide_done_overlay)
        done_btns.addWidget(continue_btn)
        dl.addLayout(done_btns)

        self._refresh_progress_label()

    def _refresh_status_label(self) -> None:
        op = "复制" if self.settings.get("operation_mode", "copy") == "copy" else "移动"
        mod_name = self.settings.get("multi_category_modifier", "Ctrl")
        wheel = "缩放" if self.settings.get("wheel_action", "zoom") == "zoom" else "切图"
        n_cats = sum(1 for c in self.project.categories if c.target_dir)
        self._status_label.setText(
            f"操作：{op}  ·  多分类：{mod_name}+分类键  ·  滚轮：{wheel}  ·  分类：{n_cats} 个"
        )

    def _rebuild_category_strip(self) -> None:
        if not hasattr(self, "_cat_strip_layout"):
            return
        layout = self._cat_strip_layout
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for cat in self.project.categories:
            if not cat.target_dir:
                continue
            btn = QPushButton(f"{cat.key}  {cat.name}")
            btn.setProperty("accent", "ghost")
            btn.setFixedHeight(28)
            layout.addWidget(btn)
        layout.addStretch(1)

    def apply_project_updates(self, project: Project,
                              settings: ProjectSettingsStore) -> None:
        """Refresh categories / cover / operation badge after project settings."""
        self.project = project
        self.settings = settings
        op = settings.get("operation_mode", "copy")
        if hasattr(self, "_op_badge"):
            self._op_badge.setText("复制" if op == "copy" else "移动")
        self._rebuild_category_strip()
        self._refresh_status_label()

    def mark_saved(self) -> None:
        if hasattr(self, "_autosave_label"):
            self._autosave_label.setText(
                "已自动保存 " + time.strftime("%H:%M:%S")
            )

    # =========================================================
    # Display / navigation
    # =========================================================
    def _show_preview_dialog(self) -> None:
        """Open the preview / starting-position dialog."""
        if not self.project.file_order:
            QApplication.beep()
            return
        paths = [Path(p) for p in self.project.file_order]
        dlg = PreviewDialog(paths, self.thumb_cache,
                            current_index=self.project.current_index,
                            parent=self)
        dlg.startingIndexChosen.connect(self._on_starting_index_chosen)
        dlg.exec()

    def _on_starting_index_chosen(self, idx: int) -> None:
        if 0 <= idx < len(self.project.file_order):
            self.project.current_index = idx
            self._show_current()
            self.saveProgressRequested.emit()

    def _toggle_category_panel(self, checked: bool) -> None:
        if checked:
            panel = CategoryPanel(self.project.categories, self)
            panel.setWindowTitle("分类与快捷键")
            panel.setWindowFlags(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
            )
            panel.adjustSize()
            # Position near the toggle button.
            btn = self._cats_btn
            global_pos = btn.mapToGlobal(btn.rect().bottomLeft())
            panel.move(global_pos.x(), global_pos.y() + 4)
            panel.show()
            self._cats_panel = panel
            # Hide panel when user clicks elsewhere or the toolbar toggle is unchecked.
            def _cleanup(*_):
                try:
                    if self._cats_panel is panel:
                        self._cats_panel = None
                except RuntimeError:
                    pass
                self._cats_btn.setChecked(False)
            panel.installEventFilter(self)
            self._cats_panel_close_handler = _cleanup
        else:
            panel = getattr(self, "_cats_panel", None)
            if panel is not None:
                try:
                    panel.close()
                except RuntimeError:
                    pass
                self._cats_panel = None

    def eventFilter(self, obj, ev):
        if getattr(self, "_cats_panel", None) is obj and ev.type() == ev.Type.Close:
            self._cats_btn.setChecked(False)
        return super().eventFilter(obj, ev)

    def _maybe_show_initial_preview(self) -> None:
        """If the project has not been started yet, pop the preview dialog."""
        if self.project.current_index < 0 and self.project.file_order:
            QTimer.singleShot(80, self._show_preview_dialog)

    def _show_project_menu(self) -> None:
        """Show project-level menu (cover, settings)."""
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        act_cover = m.addAction("设置项目封面…")
        act_clear = m.addAction("清除封面")
        m.addSeparator()
        act_settings = m.addAction("项目设置…")
        act_log = m.addAction("打开项目日志文件夹")
        chosen = m.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))
        if chosen is act_cover:
            self.coverRequested.emit()
        elif chosen is act_clear:
            self.coverCleared.emit()
        elif chosen is act_settings:
            self.projectSettingsRequested.emit()
        elif chosen is act_log:
            self.openLogRequested.emit()

    def _show_current(self) -> None:
        idx = self.project.current_index
        if idx < 0 or idx >= len(self.project.file_order):
            self.image_view.clear()
            self._refresh_progress_label()
            return
        path = Path(self.project.file_order[idx])
        self.image_view.show_path(path)
        self._refresh_exif(path)
        self._refresh_progress_label()

    def _refresh_progress_label(self) -> None:
        total = len(self.project.file_order)
        cur = self.project.current_index
        if total == 0:
            self.progress_label.setText("0 / 0")
        elif cur < 0:
            self.progress_label.setText(f"0 / {total}")
        else:
            self.progress_label.setText(f"{cur + 1} / {total}")

    def _refresh_exif(self, path: Path) -> None:
        meta = self._get_meta(path)
        for key, lbl in self._exif_labels.items():
            label_text = dict(EXIF_FIELDS)[key]
            lbl.setText(f"{label_text}: {format_exif(meta, key)}")

    def _get_meta(self, path: Path) -> dict:
        key = str(path)
        if key not in self._meta_cache:
            self._meta_cache[key] = metadata_for(path)
        return self._meta_cache[key]

    # =========================================================
    # RAW loading notification
    # =========================================================
    def _on_raw_loading(self) -> None:
        self.rawLibraryLoadStarted.emit()

    def _on_raw_loaded(self, ok: bool) -> None:
        self.rawLibraryLoadFinished.emit(ok)
        if ok:
            self._show_current()

    # =========================================================
    # Operations
    # =========================================================
    def _advance(self) -> None:
        total = len(self.project.file_order)
        if total == 0:
            return
        if self.project.current_index < total - 1:
            self.project.current_index += 1
            self._show_current()
            return
        # At last image: check start_logic for wrap behaviour.
        start_logic = self.settings.get('start_logic', 'linear')
        if start_logic == 'wrap' and total > 0:
            # Find next unclassified index, wrapping.
            nxt = (self.project.current_index + 1) % total
            self.project.current_index = nxt
            self._show_current()
        else:
            self._refresh_progress_label()

    def _back(self) -> None:
        if self.project.current_index > 0:
            self.project.current_index -= 1
            self._show_current()
        else:
            self._refresh_progress_label()

    def _jump(self, delta: int) -> None:
        total = len(self.project.file_order)
        if total == 0:
            return
        new_idx = self.project.current_index + delta
        new_idx = max(0, min(total - 1, new_idx))
        self.project.current_index = new_idx
        self._show_current()

    def _on_wheel_switch(self, direction: int) -> None:
        if direction > 0:
            self._advance()
        elif direction < 0:
            self._back()

    def _on_category(self, key: str, modifier_held: bool) -> None:
        if self.project.current_index < 0:
            return
        cats = {c.key: c for c in self.project.categories}
        cat = cats.get(key)
        if not cat or not cat.target_dir:
            QApplication.beep()
            return
        src = Path(self.project.file_order[self.project.current_index])
        if not src.exists():
            QMessageBox.warning(self, "源文件不存在", f"找不到：{src}")
            return

        op_mode = self.settings.get("operation_mode", "copy")
        if modifier_held and self.settings.get("modifier_invert_advance", True):
            effective_op = "copy"
            stay = True
        else:
            effective_op = op_mode
            stay = False

        strategy = self.settings.get("duplicate_strategy", "rename")
        target_dir = Path(cat.target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = unique_dest_path(target_dir, src.name, strategy=strategy)

        record: Optional[OperationRecord] = None
        try:
            if effective_op == "copy":
                copy_file(src, target)
                record = OperationRecord(op="copy", src_path=str(src),
                                         dst_path=str(target), category_key=key)
            else:
                move_file(src, target)
                record = OperationRecord(op="move", src_path=str(src),
                                         dst_path=str(target), category_key=key)
            self._undo_stack.push(record)
            # Track classified so auto-complete can fire.
            self.project.classified[str(src)] = key
            self.csv_logger.write(source=str(src), action=effective_op,
                                  destination=str(target), category=key, result="ok")
            # Auto-complete check
            self._maybe_auto_complete()
            # Persist progress after every operation
            self.saveProgressRequested.emit()
        except Exception as e:
            self.csv_logger.write(source=str(src), action=effective_op,
                                  destination="", category=key, result="fail", error=str(e))
            QMessageBox.warning(self, "操作失败", f"无法处理 {src.name}\n{e}")
            return

        delay = int(self.settings.get("auto_advance_delay_ms", 0) or 0)
        if stay or delay <= 0:
            if not stay:
                self._advance()
        else:
            QTimer.singleShot(delay, self._advance)

    def _on_delete(self) -> None:
        if self.project.current_index < 0:
            return
        src = Path(self.project.file_order[self.project.current_index])
        if not src.exists():
            return
        permanent = bool(self.settings.get("permanent_delete", False))
        if permanent:
            ok = delete_permanently(src)
            trash_path = None
        else:
            trash_path = move_to_app_trash(src, self._trash_root)
            ok = trash_path is not None
        if not ok:
            QMessageBox.warning(self, "删除失败", f"无法删除 {src}")
            return
        self._undo_stack.push(OperationRecord(
            op="delete", src_path=str(src),
            dst_path=str(trash_path) if trash_path else None,
            category_key=None,
        ))
        self.project.classified[str(src)] = "__deleted__"
        self.csv_logger.write(source=str(src), action="delete",
                              destination="", category="", result="ok")
        if hasattr(self, "_autosave_label"):
            self._autosave_label.setText(
                "已永久删除" if permanent else "已删除，Ctrl+Z 可恢复"
            )
        self._advance()
        self._maybe_auto_complete()
        self.saveProgressRequested.emit()

    def _on_undo(self) -> None:
        rec = self._undo_stack.pop()
        if rec is None:
            QApplication.beep()
            return
        try:
            if rec.op == "copy":
                if rec.dst_path and Path(rec.dst_path).exists():
                    Path(rec.dst_path).unlink()
                self.csv_logger.write(source=rec.src_path, action="undo_copy",
                                      destination=rec.dst_path or "", result="ok")
            elif rec.op == "move":
                if rec.dst_path and Path(rec.dst_path).exists():
                    move_file(Path(rec.dst_path), Path(rec.src_path))
                self.csv_logger.write(source=rec.src_path, action="undo_move",
                                      destination=rec.dst_path or "", result="ok")
            elif rec.op == "delete":
                dst = Path(rec.dst_path) if rec.dst_path else None
                if dst is not None and dst.exists():
                    move_file(dst, Path(rec.src_path))
                    self.csv_logger.write(
                        source=rec.src_path, action="undo_delete",
                        destination=str(dst), result="ok",
                    )
                else:
                    self.csv_logger.write(
                        source=rec.src_path, action="undo_delete",
                        destination="", result="skip",
                        error="permanent-delete",
                    )
                    QMessageBox.information(
                        self, "无法恢复",
                        "这张图是永久删除的，撤销栈无法恢复文件。",
                    )
                    return
        except Exception as e:
            self.csv_logger.write(source=rec.src_path, action=f"undo_{rec.op}",
                                  destination=rec.dst_path or "", result="fail", error=str(e))
            QMessageBox.warning(self, "撤销失败", str(e))
            return
        # Remove from classified if present
        if rec.src_path in self.project.classified:
            del self.project.classified[rec.src_path]
        # Rewind to the image that was affected
        try:
            self.project.current_index = self.project.file_order.index(rec.src_path)
        except ValueError:
            pass
        self._show_current()
        self.saveProgressRequested.emit()

    def _on_zoom_in(self) -> None:
        self.image_view.zoom_in()

    def _on_zoom_out(self) -> None:
        self.image_view.zoom_out()

    def _on_zoom_reset(self) -> None:
        self.image_view.reset_zoom()

    # =========================================================
    # Key event
    # =========================================================
    def keyPressEvent(self, e: QKeyEvent) -> None:
        # Forwarded from main window normally.
        super().keyPressEvent(e)

    def dispatch_key(self, e: QKeyEvent) -> bool:
        """Called by MainWindow. Return True if handled."""
        if self._building:
            return False
        if not self.project.file_order:
            return False
        mods = e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # Multi-category modifier
        mod_setting = self.settings.get("multi_category_modifier", "Ctrl")
        multi_mod = ((mod_setting == "Ctrl" and ctrl) or
                     (mod_setting == "Shift" and shift) or
                     (mod_setting == "Alt" and alt))

        text = e.text().upper()
        key = e.key()

        # ---- Numeric / alpha category keys ----
        # Allow the multi-category modifier (default Ctrl) plus the category key.
        # This makes Ctrl+1 / Ctrl+A trigger the multi-classify behavior while
        # plain 1 / A still does normal classify+advance.
        cats_keys = {c.key for c in self.project.categories}

        # Build a map of Qt.Key enum values to category keys for special
        # keys that have no printable text (arrow keys).
        KEY_MAP = {
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
        }
        cat_key = None
        if text in cats_keys:
            cat_key = text
        elif key in KEY_MAP and KEY_MAP[key] in cats_keys:
            cat_key = KEY_MAP[key]

        if cat_key is not None:
            # If the held modifier matches the multi-category setting, treat as multi.
            if multi_mod:
                # Never let a multi-category shortcut shadow an explicit
                # action shortcut such as Ctrl+Up (zoom in).
                action_keys = (
                    "undo_key", "delete_key", "zoom_in_key", "zoom_out_key",
                    "zoom_reset_key", "next_image_key", "prev_image_key",
                    "next_image_alt_key", "prev_image_alt_key",
                    "fullscreen_key", "preview_key", "back_to_grid_key",
                )
                if any(
                    event_matches(e, self.settings.get(k, ""))
                    for k in action_keys
                ):
                    pass  # fall through to the explicit action below
                else:
                    self._on_category(cat_key, True)
                    return True
            # If no extra modifier is held, normal operation.
            if not ctrl and not alt and not shift:
                self._on_category(cat_key, False)
                return True
            # Shift+arrow triggers normal category; bare arrow would also be caught by KEY_MAP.
            # We let shift-modified arrows fall through to nav keys (handled below).
            if not (cat_key in ("Up", "Down", "Left", "Right")):
                return False


        # ---- Settings-driven keys ----
        # Undo
        undo_key = self.settings.get("undo_key", "Ctrl+Z")
        if event_matches(e, undo_key):
            self._on_undo(); return True
        # Delete
        delete_key = self.settings.get("delete_key", "Delete")
        if event_matches(e, delete_key):
            self._on_delete(); return True
        # Zoom
        if event_matches(e, self.settings.get("zoom_in_key", "Ctrl+Up")):
            self._on_zoom_in(); return True
        if event_matches(e, self.settings.get("zoom_out_key", "Ctrl+Down")):
            self._on_zoom_out(); return True
        if event_matches(e, self.settings.get("zoom_reset_key", "Ctrl+0")):
            self._on_zoom_reset(); return True
        # Navigation
        if event_matches(e, self.settings.get("next_image_key", "Right")):
            self._advance(); return True
        if event_matches(e, self.settings.get("prev_image_key", "Left")):
            self._back(); return True
        if event_matches(e, self.settings.get("next_image_alt_key", "Down")):
            self._jump(10); return True
        if event_matches(e, self.settings.get("prev_image_alt_key", "Up")):
            self._jump(-10); return True
        if event_matches(e, self.settings.get("first_image_key", "")):
            self.project.current_index = 0; self._show_current(); return True
        if event_matches(e, self.settings.get("last_image_key", "")):
            self.project.current_index = len(self.project.file_order) - 1
            self._show_current(); return True
        # Preview / starting-position dialog (configurable, default Space)
        if event_matches(e, self.settings.get("preview_key", "Space")):
            self._show_preview_dialog(); return True
        # Esc = back
        if event_matches(e, self.settings.get("back_to_grid_key", "Escape")):
            self.closed.emit(); return True
        # Fullscreen toggle (P default) - we still want it to work, but the
        # MainWindow also has a shortcut; we don't handle it here to avoid dbl.

        return False

    # =========================================================
    # Save / complete check
    # =========================================================

    def _show_done_overlay(self) -> None:
        """Show the completion summary page."""
        counts: Dict[str, int] = {}
        for k in self.project.classified.values():
            counts[k] = counts.get(k, 0) + 1
        cat_map = {c.key: c for c in self.project.categories}
        lines = []
        for k, v in sorted(counts.items()):
            name = cat_map.get(k, type("X", (), {"name": k})).name if k in cat_map else k
            lines.append(f"  {k} {name}: {v}")
        self._done_subtitle.setText(f"项目「{self.project.name}」已全部完成。")
        stats = f"总共 {len(self.project.classified)} 张图片" + ("\n" + "\n".join(lines) if lines else "")
        self._done_stats_label.setText(stats)
        self._done_overlay.setGeometry(self.rect())
        self._done_overlay.show()
        self._done_overlay.raise_()

    def _hide_done_overlay(self) -> None:
        self._done_overlay.hide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_done_overlay") and self._done_overlay:
            self._done_overlay.setGeometry(self.rect())
    def _maybe_auto_complete(self) -> None:
        if not self.project.file_order:
            return
        total = len(self.project.file_order)
        done = len(self.project.classified)
        if done >= total and self.project.status != "completed":
            self.project.status = "completed"
            self.completeChanged.emit()
            self._show_done_overlay()
