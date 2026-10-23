# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the new WebView2 UI (preview)
# Build:  powershell -ExecutionPolicy Bypass -File .\scripts\build_webui.ps1
# Output: dist/DoDoClaw-preview/DoDoClaw.exe

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src" / "dodoclaw"

datas = [
    (str(ROOT / "config" / "settings.yaml"), "config"),
    (str(ROOT / "config" / "gamestate_integration_dodoclaw.cfg"), "config"),
    (str(ROOT / ".env.example"), "."),
    (str(SRC / "webui" / "static"), "dodoclaw/webui/static"),
    (str(SRC / "data"), "dodoclaw/data"),
]
binaries = []
hiddenimports = [
    "anyio._backends._asyncio",
    "dodoclaw.service",
    "dodoclaw.webui.app",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
]
for pkg in ("webview", "pythonnet", "clr_loader"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    [str(ROOT / "packaging" / "entry_webui.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "ruff", "matplotlib", "customtkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DoDoClaw",
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, upx=False, name="DoDoClaw-preview")
