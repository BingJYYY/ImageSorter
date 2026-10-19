"""File operations: copy, move, delete (recycle), with collision handling."""

from __future__ import annotations
import os, shutil, hashlib, time
from pathlib import Path
from typing import Optional, Tuple


def file_md5(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def unique_dest_path(dst_dir: Path, original_name: str,
                     strategy: str = "rename",
                     md5_existing: Optional[str] = None,
                     source_md5: Optional[str] = None) -> Path:
    """Return a destination path that does not collide with existing files.

    strategy:
      - rename: append " (1)", " (2)" ... (default)
      - skip:   return dst_dir / original_name even if it exists
                (caller must check existence and decide)
      - overwrite: return dst_dir / original_name (caller overwrites)
    """
    dst = dst_dir / original_name
    if not dst.exists():
        return dst
    if strategy == "overwrite":
        return dst
    if strategy == "skip":
        return dst
    if strategy == "ask":
        # caller should handle; default to rename
        pass
    # rename
    stem = Path(original_name).stem
    suffix = Path(original_name).suffix
    i = 1
    while True:
        candidate = dst_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def copy_file(src: Path, dst: Path, preserve_metadata: bool = True) -> None:
    """Binary copy. Falls back to copy2/copy."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if preserve_metadata:
        shutil.copy2(str(src), str(dst))
    else:
        shutil.copyfile(str(src), str(dst))


def move_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Try os.rename first (fast, atomic on same volume).
    try:
        os.rename(str(src), str(dst))
        return
    except OSError:
        pass
    # Cross-volume fallback: copy then delete source.
    shutil.copy2(str(src), str(dst))
    try:
        os.remove(str(src))
    except OSError:
        pass


def delete_to_recycle(path: Path) -> bool:
    """Send a file to the Windows recycle bin. Returns True on success."""
    try:
        from send2trash import send2trash
        send2trash(str(path))
        return True
    except Exception:
        return False


def delete_permanently(path: Path) -> bool:
    try:
        os.remove(str(path))
        return True
    except OSError:
        return False


def move_to_app_trash(path: Path, trash_root: Path) -> Optional[Path]:
    """Move a file into the app-managed trash so Ctrl+Z can restore it."""
    try:
        trash_root = Path(trash_root)
        trash_root.mkdir(parents=True, exist_ok=True)
        target = unique_dest_path(trash_root, Path(path).name, strategy="rename")
        move_file(Path(path), target)
        return target
    except Exception:
        return None
