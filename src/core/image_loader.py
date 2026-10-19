"""Image format registry, scanner, metadata, and lazy RAW loader.

Image formats are split into two groups:
  - basic_formats: loaded at startup (fast, small libs)
  - raw_formats:   loaded on demand when a RAW file is first encountered.
                    The user sees a one-time "loading RAW library..." overlay.

EXIF reading: we read metadata once during scan and cache it on the
Project.file_order's sidecar metadata (see project_meta.json).
"""

from __future__ import annotations
import os, json, time, threading, traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ExifTags, ImageOps, UnidentifiedImageError

# Pillow HEIF (optional but requested). We register the opener lazily so missing
# install does not break basic-format users.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False

# rawpy is heavy; import lazily.
RAW_LIB_LOCK = threading.Lock()
RAW_LIB_LOADED = False
RAW_LIB_LOADING = False


def load_raw_library(on_loading: Optional[Callable[[], None]] = None,
                     on_loaded: Optional[Callable[[], None]] = None,
                     on_error: Optional[Callable[[Exception], None]] = None) -> bool:
    """Idempotent import of rawpy. Calls callbacks from the calling thread."""
    global RAW_LIB_LOADED, RAW_LIB_LOADING
    with RAW_LIB_LOCK:
        if RAW_LIB_LOADED:
            return True
        if RAW_LIB_LOADING:
            return False
        RAW_LIB_LOADING = True
    if on_loading:
        try:
            on_loading()
        except Exception:
            pass
    try:
        import rawpy  # noqa: F401
        with RAW_LIB_LOCK:
            RAW_LIB_LOADED = True
        if on_loaded:
            try:
                on_loaded()
            except Exception:
                pass
        return True
    except Exception as e:
        with RAW_LIB_LOCK:
            RAW_LIB_LOADING = False
        if on_error:
            try:
                on_error(e)
            except Exception:
                pass
        return False


# ---- Format groups ----
BASIC_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".avif"}
HEIF_EXTS = {".heic", ".heif"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2", ".pef", ".srw", ".x3f"}

ALL_EXTS = BASIC_EXTS | HEIF_EXTS | RAW_EXTS


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in ALL_EXTS


# ---- Scanning ----
def scan_directory(root: Path, recursive: bool = True,
                   progress_cb: Optional[Callable[[int], None]] = None
                   ) -> List[Path]:
    root = Path(root)
    if not root.exists():
        return []
    out: List[Path] = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            for fn in filenames:
                p = Path(dirpath) / fn
                if is_supported(p):
                    out.append(p)
                    if progress_cb and len(out) % 500 == 0:
                        progress_cb(len(out))
    else:
        for p in root.iterdir():
            if p.is_file() and is_supported(p):
                out.append(p)
    if progress_cb:
        progress_cb(len(out))
    return out


# ---- EXIF ----
EXIF_TAGS = ExifTags.TAGS


def _exif_dict(img: Image.Image) -> Dict[str, Any]:
    try:
        raw = img.getexif()
        if raw is None:
            return {}
        out = {EXIF_TAGS.get(k, k): v for k, v in raw.items()}
        ifd = raw.get_ifd(0x8769)
        if ifd:
            for k, v in ifd.items():
                tag = EXIF_TAGS.get(k, k)
                out[tag] = v
        return out
    except Exception:
        return {}


def _read_datetime(d: Dict[str, Any]) -> Optional[str]:
    for key in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
        v = d.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _parse_dt(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            import datetime
            return datetime.datetime.strptime(s, fmt).timestamp()
        except Exception:
            continue
    return None


def _rational(v):
    """Pillow sometimes returns IFDRational. Coerce to float."""
    try:
        return float(v)
    except Exception:
        try:
            return v.numerator / v.denominator
        except Exception:
            return None


def metadata_for(path: Path) -> Dict[str, Any]:
    """Return cached metadata for an image. Cheap to call; opens the file once.

    Returns dict with keys: mtime, ctime, size, date_taken_ts, exif dict, width, height, mime.
    """
    p = Path(path)
    out: Dict[str, Any] = {
        "path": str(p),
        "mtime": p.stat().st_mtime if p.exists() else 0.0,
        "ctime": p.stat().st_ctime if p.exists() else 0.0,
        "size": p.stat().st_size if p.exists() else 0,
        "date_taken_ts": None,
        "exif": {},
        "width": 0,
        "height": 0,
        "mime": "",
    }
    ext = p.suffix.lower()
    try:
        if ext in RAW_EXTS:
            # Try embedded JPEG preview via rawpy (no full decode yet).
            try:
                with RAW_LIB_LOCK:
                    if not RAW_LIB_LOADED:
                        # without rawpy we cannot get dimensions/preview at all
                        return out
                import rawpy
                with rawpy.imread(str(p)) as raw:
                    out["width"] = int(raw.sizes.width)
                    out["height"] = int(raw.sizes.height)
                    # RAW EXIF may have DateTimeOriginal
                    try:
                        ex = raw.metadata
                        dt = getattr(ex, "datetime", None) if ex else None
                        if dt:
                            ts = _parse_dt(str(dt))
                            if ts:
                                out["date_taken_ts"] = ts
                    except Exception:
                        pass
                out["mime"] = "image/raw"
                return out
            except Exception:
                return out
        img = Image.open(str(p))
        img.load()
        out["width"], out["height"] = img.size
        out["mime"] = img.format or ""
        if ext in {".jpg", ".jpeg", ".tif", ".tiff"}:
            d = _exif_dict(img)
            out["exif"] = _stringify_exif(d)
            dt_str = _read_datetime(d)
            ts = _parse_dt(dt_str)
            if ts:
                out["date_taken_ts"] = ts
        img.close()
    except Exception:
        pass
    return out


def _stringify_exif(d: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in d.items():
        try:
            if isinstance(v, bytes) and len(v) > 256:
                out[k] = "<binary>"
            else:
                out[k] = v if isinstance(v, (str, int, float, list, bool)) else str(v)
        except Exception:
            out[k] = str(v)
    return out


# ---- Sorting key helpers ----
def sort_key(meta: Dict[str, Any], field: str, descending: bool) -> Any:
    name = Path(meta["path"]).name.lower() if field == "name" else None
    if field == "name":
        v: Any = name or ""
    elif field == "size":
        v = meta.get("size", 0)
    elif field == "date_taken":
        v = meta.get("date_taken_ts") or min(meta.get("mtime", 0), meta.get("ctime", 0))
    elif field == "created":
        v = meta.get("ctime", 0)
    elif field == "modified":
        v = meta.get("mtime", 0)
    elif field == "accessed":
        try:
            v = Path(meta["path"]).stat().st_atime
        except Exception:
            v = 0
    elif field == "type":
        ext = Path(meta["path"]).suffix.lower()
        v = ext
    elif field == "resolution":
        v = (meta.get("width", 0) or 0) * (meta.get("height", 0) or 0)
    elif field == "width":
        v = meta.get("width", 0)
    elif field == "height":
        v = meta.get("height", 0)
    elif field == "ratio":
        w = meta.get("width", 0)
        h = meta.get("height", 0)
        v = (w / h) if h else 0
    elif field == "camera_model":
        exif = meta.get("exif", {})
        v = str(exif.get("Model", "")).lower()
    else:
        v = 0
    if descending:
        # Use negation for numbers; reverse strings via custom key elsewhere.
        if isinstance(v, (int, float)):
            v = -v
    return v


def _make_sort_key_func(field: str, descending: bool):
    """Return a callable suitable for list.sort(key=...) that respects descending."""
    is_str = field in ("name", "type", "camera_model")
    f = lambda m: sort_key(m, field, False)  # we handle descending with wrapper
    if is_str:
        return lambda m: (sort_key(m, field, False),)
    return lambda m: sort_key(m, field, False)


def sort_files(files: List[Path], field: str, descending: bool) -> List[Path]:
    metas = [metadata_for(p) for p in files]
    indexed = list(zip(metas, files))
    is_str = field in ("name", "type", "camera_model")
    if is_str:
        indexed.sort(key=lambda x: (sort_key(x[0], field, False),), reverse=descending)
    else:
        indexed.sort(key=lambda x: sort_key(x[0], field, False), reverse=descending)
    return [p for _, p in indexed]


# ---- Image opening for display ----
def open_for_display(path: Path, max_pixels: int = 24_000_000) -> Image.Image:
    """Return a PIL image oriented correctly and downsampled if huge.

    For RAW files, uses the embedded JPEG preview when available; otherwise
    triggers rawpy load (caller should call load_raw_library first).
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext in RAW_EXTS:
        try:
            import rawpy
            with rawpy.imread(str(p)) as raw:
                try:
                    thumb = raw.extract_thumb()
                except Exception:
                    thumb = None
                if thumb is not None and getattr(thumb, "format", None) == "jpeg":
                    from io import BytesIO
                    img = Image.open(BytesIO(thumb.data))
                    img = ImageOps.exif_transpose(img) or img
                else:
                    rgb = raw.postprocess(demosaic_algorithm=rawpy.DemosaicAlgorithm.LINEAR,
                                          half_size=True, use_camera_wb=False, no_auto_bright=True)
                    img = Image.fromarray(rgb)
        except Exception:
            img = Image.new("RGB", (800, 600), (12, 10, 8))
    else:
        img = Image.open(str(p))
        img = ImageOps.exif_transpose(img) or img

    w, h = img.size
    if w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img
