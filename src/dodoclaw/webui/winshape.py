"""Give the frameless overlay window rounded corners on Windows.

pywebview 6.2's ``transparent=True`` on WinForms only makes the WebView2
background transparent; the top-level Form underneath still paints its default
light-grey BackColor, so every pixel the card leaves uncovered (rounded
corners, CSS shadow margin) shows up as a grey rectangle. EdgeChromium
transparent windows also stop receiving mouse/keyboard input. So the overlay
is an opaque window sized exactly to the card, and the corners are cut here:

* Win11 (build >= 22000): DWM rounds the window (anti-aliased, follows resizes).
* Win10: a rounded window region (re-applied after every resize).

All calls are one-shot Win32 calls on show/resize; nothing runs per frame.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE  # no system border; the card's own 1px CSS border shows
WIN11_BUILD = 22000
RADIUS = 8  # CSS px; matches Win11's DWM corner and .ov/.pill border-radius in overlay.html


def windows_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0


def region_radius(dpi_scale: float, radius: int = RADIUS) -> int:
    """Ellipse size for CreateRoundRectRgn (it takes the diameter, in device px)."""
    return max(2, round(2 * radius * (dpi_scale or 1.0)))


def hwnd_of(window) -> int | None:
    """HWND of a pywebview window on the WinForms backend, else None."""
    try:
        form = window.native
        return int(form.Handle.ToInt64()) if form is not None else None
    except Exception:
        return None


def round_corners(hwnd: int | None, build: int | None = None, user32=None, dwmapi=None, gdi32=None) -> str:
    """Round the window's corners. Returns "dwm", "region" or "" (nothing done)."""
    if not hwnd:
        return ""
    build = windows_build() if build is None else build
    if build <= 0:
        return ""
    import ctypes

    if user32 is None:
        user32, dwmapi, gdi32 = ctypes.windll.user32, ctypes.windll.dwmapi, ctypes.windll.gdi32
    if build >= WIN11_BUILD:
        pref = ctypes.c_int(DWMWCP_ROUND)
        try:
            hr = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)
            )
            if hr == 0:
                none = ctypes.c_uint(DWMWA_COLOR_NONE)
                dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), DWMWA_BORDER_COLOR, ctypes.byref(none), ctypes.sizeof(none)
                )
                return "dwm"
            logger.debug("DwmSetWindowAttribute corner hr=%#x, falling back to region", hr & 0xFFFFFFFF)
        except Exception:
            logger.debug("DWM corner preference failed", exc_info=True)
    return _apply_region(hwnd, user32, gdi32)


def _apply_region(hwnd: int, user32, gdi32) -> str:
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return ""
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return ""
    try:
        scale = user32.GetDpiForWindow(ctypes.c_void_p(hwnd)) / 96 or 1.0
    except Exception:
        scale = 1.0
    d = region_radius(scale)
    rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, d, d)
    if not rgn:
        return ""
    # On success the system owns the region; don't delete it.
    if not user32.SetWindowRgn(ctypes.c_void_p(hwnd), rgn, True):
        gdi32.DeleteObject(rgn)
        return ""
    return "region"
