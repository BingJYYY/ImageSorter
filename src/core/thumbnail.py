"""Thumbnail cache. Per-project, LRU by mtime, capped at max_bytes.

Each thumbnail is stored as JPEG in <source_dir>/.thumbcache/<project_id>/<hash>.jpg
where hash is sha1(absolute_path). The cache dir lives next to the source so it
moves with the project, but we keep all state inside the project's project.json
via a recorded cache_root path.
"""

from __future__ import annotations
import os, hashlib, threading, time
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageOps

from .image_loader import open_for_display


def _hash_path(p: Path) -> str:
    return hashlib.sha1(str(p.resolve()).encode("utf-8")).hexdigest()


class ThumbnailCache:
    """Per-project thumbnail cache with size cap."""

    THUMB_FORMAT = "JPEG"
    THUMB_QUALITY = 82

    def __init__(self, cache_root: Path, max_bytes: int = 0,
                 max_dimension: int = 480, max_per_image_bytes: int = 200 * 1024):
        self.root = Path(cache_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(0, int(max_bytes))
        self.max_dimension = max(64, int(max_dimension))
        self.max_per_image_bytes = max(8 * 1024, int(max_per_image_bytes))
        self._lock = threading.RLock()
        self._inflight: set = set()  # avoid duplicate concurrent generation

    def _target(self, path: Path) -> Path:
        return self.root / (_hash_path(path) + ".jpg")

    def get_or_generate(self, path: Path,
                        on_loading_raw: Optional[Callable[[], None]] = None,
                        force_regen: bool = False) -> Optional[Path]:
        target = self._target(path)
        if target.exists() and not force_regen:
            try:
                if target.stat().st_size > 0:
                    return target
                target.unlink()
            except OSError:
                pass
        with self._lock:
            if path in self._inflight:
                return None
            self._inflight.add(path)
        try:
            img = open_for_display(path, max_pixels=self.max_dimension * self.max_dimension * 4)
            try:
                # Fit inside max_dimension box (preserve aspect)
                img.thumbnail((self.max_dimension, self.max_dimension), Image.LANCZOS)
                # Encode at quality that fits the per-image byte cap.
                q = self.THUMB_QUALITY
                data = None
                for trial_q in (q, 70, 58, 46, 34):
                    buf = __import__("io").BytesIO()
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(buf, self.THUMB_FORMAT, quality=trial_q, optimize=True)
                    if buf.tell() <= self.max_per_image_bytes or trial_q == 34:
                        data = buf.getvalue()
                        break
                if data is not None:
                    tmp = target.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    os.replace(tmp, target)
            finally:
                img.close()
            self._maybe_evict()
            return target
        except Exception:
            return None
        finally:
            with self._lock:
                self._inflight.discard(path)

    def invalidate(self, path: Path) -> None:
        target = self._target(path)
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass

    def clear_all(self) -> int:
        """Delete all cached thumbnails. Returns count removed."""
        count = 0
        if not self.root.exists():
            return 0
        for p in self.root.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def total_bytes(self) -> int:
        total = 0
        if not self.root.exists():
            return 0
        for p in self.root.iterdir():
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total

    def _maybe_evict(self) -> None:
        if self.max_bytes <= 0:
            return
        total = self.total_bytes()
        if total <= self.max_bytes:
            return
        # Evict oldest files first.
        files = []
        for p in self.root.iterdir():
            if p.is_file():
                try:
                    files.append((p.stat().st_mtime, p))
                except OSError:
                    pass
        files.sort()
        for _, p in files:
            if total <= self.max_bytes:
                break
            try:
                sz = p.stat().st_size
                p.unlink()
                total -= sz
            except OSError:
                pass
