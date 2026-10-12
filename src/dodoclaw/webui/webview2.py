"""Detect the Microsoft Edge WebView2 runtime (Windows)."""

from __future__ import annotations

import os

_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"


def webview2_version() -> str | None:
    """Return the installed WebView2 runtime version, or None if missing.

    On non-Windows platforms returns "n/a" (pywebview uses another backend there).
    """
    if os.name != "nt":
        return "n/a"
    import winreg

    candidates = [
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + _CLIENT),
        (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + _CLIENT),
        (winreg.HKEY_CURRENT_USER, "Software\\" + _CLIENT),
    ]
    for root, path in candidates:
        try:
            with winreg.OpenKey(root, path) as key:
                ver, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        ver = str(ver or "").strip()
        if ver and ver != "0.0.0.0":
            return ver
    return None


def require_webview2() -> bool:
    """Show a native message box and return False when WebView2 is missing."""
    if webview2_version() is not None:
        return True
    msg = (
        "DoDoClaw 新界面需要 Microsoft Edge WebView2 运行时。\n\n"
        "Win11 自带；部分 Win10 需要手动安装（免费，约 2 分钟）。\n"
        f"下载地址：{DOWNLOAD_URL}\n\n点“确定”打开下载页。"
    )
    try:
        import ctypes
        import webbrowser

        # MB_OKCANCEL | MB_ICONWARNING
        if ctypes.windll.user32.MessageBoxW(None, msg, "缺少 WebView2", 0x1 | 0x30) == 1:
            webbrowser.open(DOWNLOAD_URL)
    except Exception:
        print(msg)
    return False
