"""Windows native hit-testing for frameless resize borders.

Returning HTLEFT/HTRIGHT/... from WM_NCHITTEST lets Windows draw the correct
resize cursor and perform the resize itself, even when the cursor is hovering a
child widget.  That is far more stable than tracking mouse moves in Qt.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor


WM_NCHITTEST = 0x0084

HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000


def enable_native_resize_border(window) -> None:
    """Add WS_THICKFRAME to a frameless window so native resizing works."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        if hasattr(user32, "GetWindowLongPtrW"):
            get_long = user32.GetWindowLongPtrW
            set_long = user32.SetWindowLongPtrW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            set_long.restype = ctypes.c_ssize_t
        else:
            get_long = user32.GetWindowLongW
            set_long = user32.SetWindowLongW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_long
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
            set_long.restype = ctypes.c_long
        style = get_long(hwnd, GWL_STYLE)
        set_long(hwnd, GWL_STYLE, style | WS_THICKFRAME)
    except Exception:
        pass


def native_hit_test(window, event_type, message, margin: int = 7
                    ) -> Optional[Tuple[bool, int]]:
    """Handle WM_NCHITTEST for a frameless window.

    Returns ``(True, ht_code)`` when the cursor is on a resize edge, otherwise
    ``None`` so Qt can continue normal event processing.
    """
    if sys.platform != "win32":
        return None
    try:
        msg = wintypes.MSG.from_address(int(message))
    except Exception:
        return None
    if msg.message != WM_NCHITTEST:
        return None
    if window.isMaximized() or window.isFullScreen():
        return None

    # Use Qt's logical cursor position so high-DPI scaling does not shift the
    # hit zones.  WM_NCHITTEST's lParam is in physical pixels.
    pos = QCursor.pos()
    geo = window.frameGeometry()
    x = pos.x() - geo.left()
    y = pos.y() - geo.top()
    w = geo.width()
    h = geo.height()
    if x < 0 or y < 0 or x >= w or y >= h:
        return None

    left = x <= margin
    right = x >= w - margin
    top = y <= margin
    bottom = y >= h - margin

    if left and top:
        code = HTTOPLEFT
    elif right and top:
        code = HTTOPRIGHT
    elif left and bottom:
        code = HTBOTTOMLEFT
    elif right and bottom:
        code = HTBOTTOMRIGHT
    elif left:
        code = HTLEFT
    elif right:
        code = HTRIGHT
    elif top:
        code = HTTOP
    elif bottom:
        code = HTBOTTOM
    else:
        return None
    return True, code
