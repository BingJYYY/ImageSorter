"""Image Sorter entry point.

When frozen (PyInstaller bundle) this module performs setup steps
*before* QtCore is imported:

1. Delete the bundled _internal\\icuuc.dll and _internal\\icudt78.dll.
   PySide6 ships ICU 78 suffixed symbols only (ucnv_open_78 etc.) while
   Qt6Core.dll asks for the un-suffixed names (ucnv_open ...). Removing
   those copies lets the Windows loader fall back to
   C:\Windows\System32\icuuc.dll, a forwarder DLL that resolves every
   symbol through icu.dll.
2. Preload icu.dll from System32 so the forwarder entries resolve at
   Qt6Core load time.
3. Patch _internal\PySide6\Qt6Core.dll import table in place so its
   WinRT API stubs (api-ms-win-core-winrt-*) point to combase.dll.

Then we delegate to src.app.main.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def _strip_bundled_icu(meipass):
    for name in ("icuuc.dll", "icudt78.dll"):
        p = meipass / name
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def _preload_system_icu():
    try:
        ctypes.CDLL("icu.dll")
    except OSError:
        pass


def _add_dll_search_dirs(meipass):
    if not hasattr(os, "add_dll_directory"):
        return
    for d in (meipass, meipass / "PySide6", meipass / "shiboken6"):
        try:
            os.add_dll_directory(str(d))
        except OSError:
            pass


def _patch_frozen_qt6core():
    try:
        from tools.patch_qt6core import patch_frozen_qt6core as _impl
    except Exception:
        return
    try:
        _impl()
    except Exception:
        pass


def _bootstrap_frozen():
    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return
    meipass_p = Path(meipass)
    _strip_bundled_icu(meipass_p)
    _preload_system_icu()
    _add_dll_search_dirs(meipass_p)
    _patch_frozen_qt6core()


_bootstrap_frozen()

from src.app import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
