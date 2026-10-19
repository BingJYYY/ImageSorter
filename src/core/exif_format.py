"""EXIF field formatting for the on-screen info bar."""

from __future__ import annotations
from typing import Any, Dict, Optional

EXIF_FIELDS = [
    ("date_taken",    "拍摄日期"),
    ("camera_model",  "拍摄机型"),
    ("lens",          "镜头"),
    ("aperture",      "光圈"),
    ("shutter",       "快门"),
    ("iso",           "ISO"),
    ("focal_length",  "焦距"),
    ("exposure_comp", "曝光补偿"),
    ("white_balance", "白平衡"),
    ("metering",      "测光"),
    ("gps",           "GPS"),
    ("resolution",    "分辨率"),
    ("file_size",     "大小"),
]


def _first(d: Dict[str, Any], *keys) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, "", b""):
            return d[k]
    return None


def _format_shutter(v: Any) -> str:
    try:
        v = float(v)
        if v <= 0:
            return "—"
        if v >= 1:
            return f"{v:.1f}s"
        return f"1/{int(round(1 / v))}s"
    except Exception:
        return str(v)


def _format_aperture(v: Any) -> str:
    try:
        v = float(v)
        return f"f/{v:.1f}"
    except Exception:
        return str(v)


def _format_focal(v: Any) -> str:
    try:
        return f"{float(v):.0f}mm"
    except Exception:
        return str(v)


def _format_iso(v: Any) -> str:
    try:
        return f"ISO {int(v)}"
    except Exception:
        return str(v)


def _format_exp_comp(v: Any) -> str:
    try:
        v = float(v)
        return f"{v:+.1f}EV"
    except Exception:
        return str(v)


def _format_datetime(ts: Optional[float]) -> str:
    if not ts:
        return "—"
    import datetime
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"


def _format_size(b: int) -> str:
    if b <= 0:
        return "—"
    if b < 1024:
        return f"{b}B"
    if b < 1024 * 1024:
        return f"{b/1024:.1f}KB"
    if b < 1024 * 1024 * 1024:
        return f"{b/1024/1024:.2f}MB"
    return f"{b/1024/1024/1024:.2f}GB"


def _format_gps(exif: Dict[str, Any]) -> str:
    lat = exif.get("GPSLatitude")
    lon = exif.get("GPSLongitude")
    if not lat and not lon:
        return "—"
    return "有定位"


def format_exif(meta: Dict[str, Any], field_key: str) -> str:
    """Return the display string for a given field. Returns '—' if unknown."""
    exif = meta.get("exif", {}) or {}
    if field_key == "date_taken":
        return _format_datetime(meta.get("date_taken_ts"))
    if field_key == "camera_model":
        v = _first(exif, "Model")
        return str(v) if v else "—"
    if field_key == "lens":
        v = _first(exif, "LensModel", "Lens", "LensMake")
        return str(v) if v else "—"
    if field_key == "aperture":
        v = _first(exif, "FNumber", "ApertureValue", "FocalLengthIn35mmFilm")
        return _format_aperture(v) if v else "—"
    if field_key == "shutter":
        v = _first(exif, "ExposureTime")
        return _format_shutter(v) if v else "—"
    if field_key == "iso":
        v = _first(exif, "ISOSpeedRatings", "ISO")
        return _format_iso(v) if v else "—"
    if field_key == "focal_length":
        v = _first(exif, "FocalLength", "FocalLengthIn35mmFilm")
        return _format_focal(v) if v else "—"
    if field_key == "exposure_comp":
        v = _first(exif, "ExposureBiasValue")
        return _format_exp_comp(v) if v else "—"
    if field_key == "white_balance":
        v = exif.get("WhiteBalance")
        return str(v) if v not in (None, "") else "—"
    if field_key == "metering":
        v = exif.get("MeteringMode")
        return str(v) if v not in (None, "") else "—"
    if field_key == "gps":
        return _format_gps(exif)
    if field_key == "resolution":
        w, h = meta.get("width", 0), meta.get("height", 0)
        return f"{w}×{h}" if w and h else "—"
    if field_key == "file_size":
        return _format_size(meta.get("size", 0))
    return "—"
