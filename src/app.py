"""Main application window. Stitches together task list, new project wizard, filter view."""

from __future__ import annotations
import sys, os, time, shutil, zipfile, json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QTimer, QSettings
from PySide6.QtGui import QIcon, QKeyEvent, QAction, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QFileDialog,
    QMessageBox, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QFrame, QSystemTrayIcon, QMenu, QMenuBar,
)

from .core.project import Project, ProjectStore, new_project_id
from .core.settings_store import GlobalSettings, ProjectSettingsStore
from .core.thumbnail import ThumbnailCache
from .core.csv_log import CsvLogger
from .core.image_loader import load_raw_library
from .ui.fonts import register_app_fonts, current_family
from .ui.styles import build_stylesheet
from .ui.task_list import TaskListPage
from .ui.new_project import NewProjectWizard
from .ui.filter_view import FilterView
from .ui.settings_dialog import SettingsDialog
from .ui.cover_picker import CoverPickerDialog
from .ui.widgets.title_bar import FramelessWindow
from .ui.icon import apply_app_icon
from .ui import colors as C


APP_DIR = Path(__file__).resolve().parent.parent


class MainWindow(FramelessWindow):
    def __init__(self, app_dir: Path, project_id: Optional[str] = None,
                 settings_override: Optional[GlobalSettings] = None):
        super().__init__(title=f"图片筛选 v{__version__()}")
        self.app_dir = Path(app_dir)
        self.gs = settings_override or GlobalSettings(self.app_dir)
        self.store = ProjectStore(self.app_dir)
        self.settings: Optional[ProjectSettingsStore] = None
        self._thumb_cache: Optional[ThumbnailCache] = None
        self._thumb_cache_pid: Optional[str] = None
        self._filter_view: Optional[FilterView] = None
        self._csv_logger: Optional[CsvLogger] = None
        self._csv_logger_pid: Optional[str] = None
        self._restore_window_state()
        self._build()
        self._setup_menus()
        self._setup_shortcuts()
        self._maybe_load_initial_project(project_id)
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self._save_pending_progress)
        self._save_timer.start()

    def _build(self) -> None:
        self.setMinimumSize(QSize(960, 640))
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.task_page = TaskListPage(self.store, self)
        self.task_page.openProject.connect(self._open_project)
        self.task_page.openProjectInNewWindow.connect(self._open_in_new_window)
        self.task_page.createNewProject.connect(self._new_project)
        self.task_page.deleteProject.connect(self._delete_project)
        self.task_page.renameProject.connect(self._rename_project)
        self.task_page.editProject.connect(self._edit_project)
        self.task_page.markProjectCompleted.connect(lambda pid: self._set_status(pid, "completed"))
        self.task_page.markProjectInProgress.connect(lambda pid: self._set_status(pid, "in_progress"))
        self.task_page.openProjectSourceDir.connect(self._open_source_dir)
        self.task_page.exportProject.connect(self._export_project)
        self.task_page.projectSettingsRequested.connect(self._open_project_settings)
        self.task_page.setCoverRequested.connect(self._set_cover_for)
        self.stack.addWidget(self.task_page)
        self.new_page = NewProjectWizard(self.gs, self)
        self.new_page.projectCreated.connect(self._on_new_project_created)
        self.stack.addWidget(self.new_page)
        self._filter_placeholder = QLabel("加载中…", self)
        self._filter_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._filter_placeholder.setStyleSheet(f"color: {C.TEXT_MUTED}; font-size: 18px;")
        self.stack.addWidget(self._filter_placeholder)
        self.statusBar().showMessage("就绪")
        self.stack.setCurrentWidget(self.task_page)

    def _setup_menus(self) -> None:
        mb = self.menuBar()
        file_menu = mb.addMenu("文件(&F)")
        new_act = QAction("新建项目(&N)", self)
        new_act.setShortcut("Ctrl+N")
        new_act.triggered.connect(self._new_project)
        file_menu.addAction(new_act)
        task_act = QAction("返回任务列表(&H)", self)
        task_act.setShortcut("Ctrl+H")
        task_act.triggered.connect(self._go_task_list)
        file_menu.addAction(task_act)
        file_menu.addSeparator()
        open_log = QAction("打开日志目录", self)
        open_log.triggered.connect(lambda: self._open_in_explorer(self.app_dir / "logs"))
        file_menu.addAction(open_log)
        open_data = QAction("打开软件数据目录", self)
        open_data.triggered.connect(lambda: self._open_in_explorer(self.app_dir))
        file_menu.addAction(open_data)
        file_menu.addSeparator()
        quit_act = QAction("退出(&Q)", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)
        edit_menu = mb.addMenu("编辑(&E)")
        self._undo_act = QAction("撤销(&U)", self)
        self._undo_act.triggered.connect(self._global_undo)
        edit_menu.addAction(self._undo_act)
        edit_menu.aboutToShow.connect(self._refresh_undo_shortcut)
        settings_menu = mb.addMenu("设置(&S)")
        global_set = QAction("全局设置…", self)
        global_set.triggered.connect(self.show_settings)
        settings_menu.addAction(global_set)
        proj_set = QAction("当前项目设置…", self)
        proj_set.triggered.connect(self._open_project_settings_current)
        settings_menu.addAction(proj_set)
        help_menu = mb.addMenu("帮助(&H)")
        about = QAction("关于", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _refresh_undo_shortcut(self) -> None:
        if not hasattr(self, "_undo_act"):
            return
        if self.settings is not None:
            key = self.settings.get("undo_key", "Ctrl+Z")
        else:
            key = self.gs.get("undo_key", "Ctrl+Z")
        self._undo_act.setShortcut(key)

    def _refresh_menus_for_project(self) -> None:
        self._refresh_undo_shortcut()

    def _setup_shortcuts(self) -> None:
        fk = self.gs.get("fullscreen_key", "P")
        act = QAction("全屏", self)
        act.setShortcut(fk)
        act.triggered.connect(self._toggle_fullscreen)
        self.addAction(act)

    def _qsettings(self) -> QSettings:
        return QSettings(str(self.app_dir / "window.ini"), QSettings.Format.IniFormat)

    def _restore_window_state(self) -> None:
        qs = self._qsettings()
        geo = qs.value("geometry")
        if geo:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass
        state = qs.value("windowState")
        if state:
            try:
                self.restoreState(state)
            except Exception:
                pass
        if not geo:
            self.resize(1280, 860)

    def _save_window_state(self) -> None:
        qs = self._qsettings()
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("windowState", self.saveState())
        qs.setValue("size", self.size())

    def _go_task_list(self) -> None:
        self.stack.setCurrentWidget(self.task_page)
        self.task_page.refresh()
        self._refresh_menus_for_project()

    def _new_project(self) -> None:
        self.stack.setCurrentWidget(self.new_page)

    def _refresh_menu_for_current(self) -> None:
        self._refresh_menus_for_project()

    def _edit_project(self, pid: str) -> None:
        self._open_project(pid)

    def _delete_project(self, pid: str) -> None:
        reply = QMessageBox.question(
            self, "删除项目",
            "确定要删除这个项目吗？（项目文件将被永久移除）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete(pid)
            if self._filter_view and self._filter_view.project and self._filter_view.project.id == pid:
                self._close_filter_view()
            self.task_page.refresh()

    def _rename_project(self, pid: str) -> None:
        proj = self.store.load_project(pid)
        if not proj:
            return
        new_name, ok = self._prompt_text("重命名项目", "新名称:", proj.name)
        if not ok or not new_name.strip():
            return
        proj.name = new_name.strip()
        self.store.save_project(proj)
        self.task_page.refresh()

    def _set_status(self, pid: str, status: str) -> None:
        proj = self.store.load_project(pid)
        if not proj:
            return
        proj.status = status
        self.store.save_project(proj)
        self.task_page.refresh()

    def _open_source_dir(self, pid: str) -> None:
        proj = self.store.load_project(pid)
        if proj and Path(proj.source_dir).exists():
            self._open_in_explorer(proj.source_dir)

    def _export_project(self, pid: str) -> None:
        proj = self.store.load_project(pid)
        if not proj:
            return
        fmt = self.gs.get("backup_format", "zip")
        from PySide6.QtWidgets import QInputDialog
        items = [("ZIP 压缩包", "zip"), ("文件夹结构", "folder"), ("两者都保存", "both")]
        labels = [label for label, _ in items]
        values = [v for _, v in items]
        idx = values.index(fmt) if fmt in values else 0
        choice, ok = QInputDialog.getItem(
            self, "导出/备份项目", "选择备份格式:", labels, idx, False
        )
        if not ok:
            return
        chosen = values[labels.index(choice)]
        target, _ = QFileDialog.getSaveFileName(
            self, "选择备份保存位置",
            str(Path.home() / f"{proj.name}-backup"),
            "Backup (*.zip)" if chosen in ("zip", "both") else "Folder",
        )
        if not target:
            return
        target_p = Path(target)
        if chosen in ("zip", "both"):
            self._export_project_zip(proj, target_p.with_suffix(".zip"))
        if chosen in ("folder", "both"):
            self._export_project_folder(proj, target_p)
        QMessageBox.information(self, "导出完成", f"已保存到：{target_p}")

    def _export_project_zip(self, proj: Project, zip_path: Path) -> None:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(proj.to_dict(), ensure_ascii=False, indent=2))
            log_path = self.store.project_file(proj.id).parent / "log.csv"
            if log_path.exists():
                zf.write(str(log_path), "log.csv")
        self.statusBar().showMessage(f"已导出 ZIP: {zip_path}", 4000)

    def _export_project_folder(self, proj: Project, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "project.json").write_text(
            json.dumps(proj.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log_path = self.store.project_file(proj.id).parent / "log.csv"
        if log_path.exists():
            shutil.copy2(str(log_path), str(folder / "log.csv"))
        self.statusBar().showMessage(f"已导出文件夹: {folder}", 4000)

    def _on_new_project_created(self, pid: str) -> None:
        if not pid:
            self.stack.setCurrentWidget(self.task_page)
            return
        pending = self.new_page.take_pending_project()
        if pending is None:
            self.stack.setCurrentWidget(self.task_page)
            return
        self.store.save_project(pending)
        self.task_page.refresh()
        self._open_project(pending.id)

    def _open_in_new_window(self, pid: str) -> None:
        import subprocess
        cmd = [sys.executable, "-m", "src.main", "--project-id", pid]
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--project-id", pid]
        try:
            subprocess.Popen(cmd, cwd=str(self.app_dir))
        except Exception as e:
            QMessageBox.warning(self, "启动失败", str(e))

    def _open_project(self, pid: str) -> None:
        proj_obj = self.store.load_project(pid)
        if proj_obj is None:
            QMessageBox.warning(self, "项目不存在", f"找不到项目：{pid}")
            return
        proj_dir = self.store.projects_dir / pid
        ps = ProjectSettingsStore(proj_dir / "project_settings.json", self.gs)
        ps.import_legacy_overrides(proj_dir / "project.json")
        legacy_cats = ps.all_override().get("project_categories")
        if legacy_cats:
            from .core.project import Category as _Category
            migrated = []
            for entry in legacy_cats:
                if isinstance(entry, dict) and entry.get("target_dir"):
                    migrated.append(_Category(**entry))
            if migrated:
                proj_obj.categories = migrated
                self.store.save_project(proj_obj)
            ps.clear_override("project_categories")
            ps.save()
        self.settings = ps
        if self._thumb_cache is None or self._thumb_cache_pid != pid:
            cache_root = self.app_dir / "thumbcache" / pid
            self._thumb_cache = ThumbnailCache(
                cache_root,
                max_bytes=self.gs.get("thumb_cache_max_bytes", 0),
                max_dimension=int(self.gs.get("thumb_max_dimension", 480)),
                max_per_image_bytes=int(self.gs.get("thumb_max_per_image_bytes", 200 * 1024)),
            )
            self._thumb_cache_pid = pid
        if self._csv_logger is None or self._csv_logger_pid != pid:
            if self._csv_logger is not None:
                try:
                    self._csv_logger.close()
                except Exception:
                    pass
            log_dir = self.store.projects_dir / pid
            log_dir.mkdir(parents=True, exist_ok=True)
            self._csv_logger = CsvLogger(log_dir / "log.csv")
            self._csv_logger_pid = pid
        self._filter_view = FilterView(
            proj_obj, ps, self._thumb_cache, self._csv_logger,
            trash_root=self.app_dir / "trash" / pid,
        )
        self._filter_view.closed.connect(self._close_filter_view)
        self._filter_view.saveProgressRequested.connect(self._save_pending_progress)
        self._filter_view.completeChanged.connect(lambda: self.store.save_project(self._filter_view.project))
        self._filter_view.coverRequested.connect(self._set_cover)
        self._filter_view.coverCleared.connect(self._clear_cover)
        self._filter_view.projectSettingsRequested.connect(lambda: self._open_project_settings(pid))
        self._filter_view.openLogRequested.connect(self._open_project_log)
        if self.stack.indexOf(self._filter_view) < 0:
            self.stack.addWidget(self._filter_view)
        self.stack.setCurrentWidget(self._filter_view)
        self._refresh_menus_for_project()

    def _close_filter_view(self) -> None:
        if self._filter_view and self._filter_view.project:
            self.store.save_project(self._filter_view.project)
        self._go_task_list()

    def _open_in_explorer(self, path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                import subprocess as _sp
                _sp.Popen(["open", str(path)])
            else:
                import subprocess as _sp
                _sp.Popen(["xdg-open", str(path)])
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    def _save_pending_progress(self) -> None:
        if self._filter_view and self._filter_view.project:
            self.store.save_project(self._filter_view.project)
            self._filter_view.mark_saved()

    def _close_csv(self) -> None:
        if self._csv_logger:
            try:
                self._csv_logger.close()
            except Exception:
                pass
            self._csv_logger = None

    def _prompt_text(self, title: str, label: str, default: str = ""):
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getText(self, title, label, text=default)

    def _prompt_choice(self, title: str, label: str, options, default: int = 0):
        from PySide6.QtWidgets import QInputDialog
        return QInputDialog.getItem(self, title, label, options, default, False)

    def _clear_cover(self) -> None:
        if not (self._filter_view and self._filter_view.project):
            return
        self._filter_view.project.cover_image = None
        self.store.save_project(self._filter_view.project)
        self.statusBar().showMessage("已清除项目封面", 3000)

    def _open_project_log(self) -> None:
        if not (self._filter_view and self._filter_view.project):
            return
        log_dir = self.store.projects_dir / self._filter_view.project.id
        self._open_in_explorer(log_dir)

    def _set_cover(self) -> None:
        if not (self._filter_view and self._filter_view.project):
            return
        proj = self._filter_view.project
        dlg = CoverPickerDialog(proj, self._thumb_cache, self)
        if dlg.exec():
            proj.cover_image = str(dlg.result_path) if dlg.result_path else None
            self.store.save_project(proj)

    def _set_cover_for(self, pid: str) -> None:
        proj = self.store.load_project(pid)
        if not proj:
            return
        if self._thumb_cache is None or self._thumb_cache_pid != pid:
            self._thumb_cache = ThumbnailCache(
                self.app_dir / "thumbcache" / pid,
                max_bytes=self.gs.get("thumb_cache_max_bytes", 0),
                max_dimension=int(self.gs.get("thumb_max_dimension", 480)),
                max_per_image_bytes=int(
                    self.gs.get("thumb_max_per_image_bytes", 200 * 1024)
                ),
            )
            self._thumb_cache_pid = pid
        dlg = CoverPickerDialog(proj, self._thumb_cache, self)
        if dlg.exec():
            proj.cover_image = str(dlg.result_path) if dlg.result_path else None
            self.store.save_project(proj)
            self.task_page.refresh()

    def _open_project_settings(self, pid: str) -> None:
        if (
            self._filter_view is not None
            and self._filter_view.project.id == pid
        ):
            self.store.save_project(self._filter_view.project)
        proj = self.store.load_project(pid)
        if not proj:
            return
        proj_dir = self.store.projects_dir / pid
        ps = ProjectSettingsStore(proj_dir / "project_settings.json", self.gs)
        ps.import_legacy_overrides(proj_dir / "project.json")
        if self._thumb_cache is None or self._thumb_cache_pid != pid:
            self._thumb_cache = ThumbnailCache(
                self.app_dir / "thumbcache" / pid,
                max_bytes=self.gs.get("thumb_cache_max_bytes", 0),
                max_dimension=int(self.gs.get("thumb_max_dimension", 480)),
                max_per_image_bytes=int(
                    self.gs.get("thumb_max_per_image_bytes", 200 * 1024)
                ),
            )
            self._thumb_cache_pid = pid
        dlg = SettingsDialog(
            self.gs, ps,
            project=proj,
            project_store=self.store,
            thumb_cache=self._thumb_cache,
            parent=self,
        )
        dlg.exec()
        updated = self.store.load_project(pid)
        if updated is None:
            return
        ps_final = ProjectSettingsStore(
            proj_dir / "project_settings.json", self.gs
        )
        if self._filter_view and self._filter_view.project.id == pid:
            self.settings = ps_final
            self._filter_view.apply_project_updates(updated, ps_final)
        self.task_page.refresh()

    def _open_project_settings_current(self) -> None:
        if self._filter_view and self._filter_view.project:
            self._open_project_settings(self._filter_view.project.id)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        current = self.stack.currentWidget()
        if isinstance(current, FilterView) and current.dispatch_key(e):
            return
        super().keyPressEvent(e)

    def _about(self) -> None:
        from . import __version__, __app_name__
        QMessageBox.about(
            self, "关于",
            f"<h3>{__app_name__}</h3>"
            f"<p>版本：v{__version__}</p>"
            "<p>Python + PySide6 + rawpy 构建。</p>"
            "<p>单文件夹便携，可直接拷贝到任意 Win10/11 电脑使用。</p>"
        )

    def show_settings(self) -> None:
        dlg = SettingsDialog(self.gs, project_store=self.store, parent=self)
        dlg.settingsChanged.connect(self._on_global_settings_changed)
        dlg.exec()

    def _on_global_settings_changed(self) -> None:
        self._apply_stylesheet()

    def _apply_stylesheet(self) -> None:
        gold = self.gs.get("theme_accent_gold", C.ACCENT_GOLD)
        rust = self.gs.get("theme_accent_rust", C.ACCENT_RUST)
        fs = int(self.gs.get("font_size", 14))
        family = current_family()
        self.setStyleSheet(build_stylesheet(gold, rust, fs, family))
        QApplication.instance().setStyleSheet(
            build_stylesheet(gold, rust, fs, family)
        )

    def _maybe_load_initial_project(self, pid) -> None:
        if pid:
            self._open_project(pid)
            return
        mode = self.gs.get("startup_mode", "task_list")
        if mode == "auto_resume":
            metas = self.store.list_all()
            in_progress = [m for m in metas if m.get("status") == "in_progress"]
            if in_progress:
                in_progress.sort(key=lambda m: m.get("last_activity", 0), reverse=True)
                self._open_project(in_progress[0]["id"])

    def _global_undo(self) -> None:
        if self._filter_view:
            self._filter_view._on_undo()

    def closeEvent(self, e) -> None:
        if self._filter_view and self._filter_view.project:
            self.store.save_project(self._filter_view.project)
        self._close_csv()
        self._save_window_state()
        super().closeEvent(e)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default=None)
    args, _ = parser.parse_known_args()

    app = QApplication(sys.argv)
    apply_app_icon(app)
    family = register_app_fonts()
    if not family:
        print("warn: bundled font not loaded, fallback to system")
    gs = GlobalSettings(APP_DIR)
    gold = gs.get("theme_accent_gold", C.ACCENT_GOLD)
    rust = gs.get("theme_accent_rust", C.ACCENT_RUST)
    fs = int(gs.get("font_size", 14))
    app.setStyleSheet(build_stylesheet(gold, rust, fs, family or "AppCJK"))

    raw_mode = gs.get("raw_load_mode", "on_demand")
    if raw_mode == "on_startup":
        load_raw_library()

    win = MainWindow(APP_DIR, project_id=args.project_id, settings_override=gs)
    win._apply_stylesheet()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


def __version__() -> str:
    from . import __version__ as v
    return v
