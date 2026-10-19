"""Detect category hotkeys that collide with global action shortcuts."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .settings_store import DEFAULTS


ACTION_LABELS = {
    "next_image_key": "下一张",
    "prev_image_key": "上一张",
    "next_image_alt_key": "下一张（备用）",
    "prev_image_alt_key": "上一张（备用）",
    "first_image_key": "第一张",
    "last_image_key": "最后一张",
    "back_to_grid_key": "返回任务列表",
    "fullscreen_key": "切换全屏",
    "undo_key": "撤销",
    "delete_key": "删除",
    "zoom_in_key": "放大",
    "zoom_out_key": "缩小",
    "zoom_reset_key": "缩放重置",
    "preview_key": "预览",
}

_MOD_ALIASES = {
    "control": "ctrl",
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "meta": "win",
    "win": "win",
}

_MOD_ORDER = {"ctrl": 0, "shift": 1, "alt": 2, "win": 3}


def normalize_shortcut(value: str) -> str:
    """Return a canonical representation such as ``ctrl+z``."""
    raw = (value or "").strip()
    if not raw:
        return ""
    parts = [p.strip().lower() for p in raw.split("+") if p.strip()]
    if not parts:
        return ""
    mods = []
    base_parts = []
    for part in parts:
        if part in _MOD_ALIASES:
            mods.append(_MOD_ALIASES[part])
        else:
            base_parts.append(part)
    mods = sorted(set(mods), key=lambda m: _MOD_ORDER.get(m, 99))
    base = "+".join(base_parts)
    return "+".join(mods + ([base] if base else []))


def find_category_conflicts(categories: Iterable, settings: Dict,
                            multi_modifier: str = "Ctrl") -> List[str]:
    """Return human-readable conflict messages for category hotkeys.

    A category hotkey is checked both as-is and together with the multi-category
    modifier, because Ctrl+<key> is a valid classification gesture and may
    collide with an action such as Ctrl+Up (zoom in).
    """
    errors: List[str] = []
    seen: Dict[str, str] = {}

    navigation_keys = {
        "next_image_key", "prev_image_key",
        "next_image_alt_key", "prev_image_alt_key",
        "first_image_key", "last_image_key",
    }
    action_map: Dict[str, tuple[str, str]] = {}
    for key, label in ACTION_LABELS.items():
        raw = settings.get(key, DEFAULTS.get(key, ""))
        norm = normalize_shortcut(raw)
        if norm:
            action_map[norm] = (label, key)

    modifier = normalize_shortcut(multi_modifier)
    for cat in categories:
        key = (getattr(cat, "key", "") or "").strip()
        name = (getattr(cat, "name", "") or key).strip()
        if not key:
            continue
        norm = normalize_shortcut(key)
        if not norm:
            continue
        if norm in seen:
            errors.append(
                f"分类「{name}」和「{seen[norm]}」使用了相同快捷键 {key}"
            )
        else:
            seen[norm] = name

        if norm in action_map and action_map[norm][1] not in navigation_keys:
            errors.append(
                f"分类「{name}」的快捷键 {key} 与「{action_map[norm][0]}」冲突"
            )

        if "+" not in norm and modifier:
            combo = normalize_shortcut(f"{modifier}+{key}")
            if combo in action_map:
                errors.append(
                    f"分类「{name}」的 {multi_modifier}+{key} 与"
                    f"「{action_map[combo][0]}」冲突"
                )
    return errors
