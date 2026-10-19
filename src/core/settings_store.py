"""Persistent settings store: global defaults + per-project overrides.

Settings live in two locations:
  - global:   <app>/settings.json
  - per-project: <project_dir>/project.json (only the project override section)

Both are merged at runtime via ProjectSettingsStore. Per-project values shadow
global ones. Missing keys fall back to DEFAULTS below.
"""

from __future__ import annotations
import json, os, threading, copy
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_NAME = "图片筛选"
APP_VERSION = "1.0.2"

# Default key/UI strings used by both layers
DEFAULTS: Dict[str, Any] = {
    # ----------------- General -----------------
    "language": "zh_CN",
    "font_size": 14,
    "theme_accent_gold": "#D0A372",
    "theme_accent_rust": "#B36953",
    "background_blur": 0,        # 0 = off, 1..20 = blur radius
    "background_transparency": 100,  # 100 = fully opaque

    # ----------------- Startup -----------------
    "startup_mode": "task_list",   # "task_list" or "auto_resume"
    "raw_load_mode": "on_demand",   # "on_demand" or "on_startup"

    # ----------------- Sorting -----------------
    "default_sort_field": "name",
    "default_sort_descending": False,

    # ----------------- Source scan -----------------
    "scan_recursive": True,

    # ----------------- Filtering -----------------
    "operation_mode": "copy",       # "copy" or "move"
    "start_logic": "linear",          # "linear" or "loop"
    "auto_advance": True,
    "auto_advance_delay_ms": 0,
    "duplicate_strategy": "rename", # "rename" | "skip" | "overwrite" | "ask"
    "use_md5_dedup": False,

    # ----------------- Categories -----------------
    # Categories are created manually per project; no global presets.
    "category_keys": [],
    "multi_category_modifier": "Ctrl",  # "Ctrl" | "Shift" | "Alt"
    "modifier_invert_advance": True,    # when modifier held, do NOT advance

    # ----------------- Undo -----------------
    "undo_stack_depth": 100,
    "undo_key": "Ctrl+Z",

    # ----------------- Navigation -----------------
    "next_image_key": "Right",
    "prev_image_key": "Left",
    "next_image_alt_key": "Down",      # Down arrow in single view = +10
    "prev_image_alt_key": "Up",        # Up arrow in single view = -10
    "first_image_key": "",             # disabled by default
    "last_image_key": "",              # disabled by default
    "back_to_grid_key": "Escape",
    "fullscreen_key": "P",
    "preview_key": "Space",

    # ----------------- Zoom -----------------
    "zoom_default_action": "wheel",    # "wheel" | "key"
    "zoom_in_key": "Ctrl+Up",
    "zoom_out_key": "Ctrl+Down",
    "zoom_reset_key": "Ctrl+0",
    "wheel_action": "zoom",            # "zoom" | "switch_image"
    "wheel_modifier_for_alt": "Ctrl",  # when wheel_action=switch_image, Ctrl+wheel = zoom

    # ----------------- Delete -----------------
    "delete_key": "Delete",
    "delete_to_recycle": True,
    "permanent_delete": False,

    # ----------------- EXIF info bar -----------------
    "exif_bar_visible": True,
    "exif_fields": {
        "date_taken": True,
        "camera_model": True,
        "lens": True,
        "aperture": True,
        "shutter": True,
        "iso": True,
        "focal_length": True,
        "exposure_comp": False,
        "white_balance": False,
        "metering": False,
        "gps": False,
        "resolution": True,
        "file_size": True,
    },

    # ----------------- Thumbnail cache -----------------
    "thumb_cache_max_bytes": 0,        # 0 = unlimited
    "thumb_max_per_image_bytes": 200 * 1024,  # 200 KB per thumbnail
    "thumb_max_dimension": 480,

    # ----------------- Export / Backup -----------------
    "backup_format": "zip",           # "zip" | "folder" | "both"
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class GlobalSettings:
    """Singleton-ish wrapper around the global settings.json file."""

    def __init__(self, app_dir: Path):
        self.app_dir = Path(app_dir)
        self.path = self.app_dir / "settings.json"
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    self._data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    self._data = {}
            else:
                self._data = {}
            self._data = _deep_merge(DEFAULTS, self._data)

    def save(self) -> None:
        with self._lock:
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def all(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur = self._data
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return copy.deepcopy(cur)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            parts = key.split(".")
            cur = self._data
            for p in parts[:-1]:
                if p not in cur or not isinstance(cur[p], dict):
                    cur[p] = {}
                cur = cur[p]
            cur[parts[-1]] = value

    def reset_to_defaults(self) -> None:
        with self._lock:
            self._data = copy.deepcopy(DEFAULTS)


class ProjectSettingsStore:
    """Per-project overrides, merged on top of a GlobalSettings instance."""

    def __init__(self, project_file: Path, global_settings: GlobalSettings):
        self.path = Path(project_file)
        self._global = global_settings
        self._lock = threading.RLock()
        self._override: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    self._override = json.loads(self.path.read_text(encoding="utf-8"))
                    if not isinstance(self._override, dict):
                        self._override = {}
                except Exception:
                    self._override = {}
            else:
                self._override = {}

    def save(self) -> None:
        with self._lock:
            self.path.write_text(
                json.dumps(self._override, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def all_override(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._override)

    def merged(self) -> Dict[str, Any]:
        """Full effective settings (global defaults + project override)."""
        with self._lock:
            return _deep_merge(self._global.all(), self._override)

    def get(self, key: str, default: Any = None) -> Any:
        merged = self.merged()
        cur = merged
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return copy.deepcopy(cur)

    def set_override(self, key: str, value: Any) -> None:
        with self._lock:
            parts = key.split(".")
            cur = self._override
            for p in parts[:-1]:
                if p not in cur or not isinstance(cur[p], dict):
                    cur[p] = {}
                cur = cur[p]
            cur[parts[-1]] = value

    def clear_override(self, key: str) -> None:
        with self._lock:
            parts = key.split(".")
            cur = self._override
            for p in parts[:-1]:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                else:
                    return
            if isinstance(cur, dict) and parts[-1] in cur:
                del cur[parts[-1]]

    def reset_to_global(self) -> None:
        with self._lock:
            self._override = {}

    def import_legacy_overrides(self, legacy_project_file: Path) -> None:
        """Move old override keys out of a polluted project.json.

        Older builds stored project settings in the same project.json as the
        project data.  Read any non-project keys once and keep them here.
        """
        if self.path.exists() or not legacy_project_file.exists():
            return
        project_fields = {
            "id", "name", "source_dir", "recursive", "operation_mode",
            "sort_field", "sort_descending", "categories", "created_at",
            "updated_at", "status", "cover_image", "file_order",
            "current_index", "classified", "history", "last_activity",
        }
        try:
            data = json.loads(legacy_project_file.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        overrides = {k: v for k, v in data.items() if k not in project_fields}
        if overrides:
            self._override = overrides
            self.save()
