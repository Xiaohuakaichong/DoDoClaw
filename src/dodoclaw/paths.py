from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Read-only resources shipped with the app (PyInstaller _MEIPASS or repo root)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # src/dodoclaw/paths.py -> repo root
    return Path(__file__).resolve().parents[2]


def app_dir() -> Path:
    """Writable directory for .env / logs / user config.

    Frozen: next to the .exe (portable).
    Dev: repository root.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Optional AppData location (for future non-portable installs)."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "DoDoClaw"
    return Path.home() / ".dodoclaw"


def config_dir() -> Path:
    """Prefer user-writable config next to app; fall back to bundled."""
    user_cfg = app_dir() / "config"
    if user_cfg.exists():
        return user_cfg
    bundled = bundle_dir() / "config"
    if bundled.exists():
        return bundled
    return user_cfg


def ensure_runtime_dirs() -> None:
    root = app_dir()
    for rel in ("logs", "data/cache", "config"):
        (root / rel).mkdir(parents=True, exist_ok=True)


def ensure_user_config_seeded() -> None:
    """Copy bundled defaults next to the app on first run (frozen portable layout)."""
    ensure_runtime_dirs()
    bundled = bundle_dir() / "config"
    target = app_dir() / "config"
    if not bundled.exists():
        return
    # New users get the template (settings.default.yaml); an existing settings.yaml is never touched.
    seeds = {
        "settings.yaml": ("settings.default.yaml", "settings.yaml"),
        "gamestate_integration_dodoclaw.cfg": ("gamestate_integration_dodoclaw.cfg",),
    }
    for name, sources in seeds.items():
        dest = target / name
        if dest.exists():
            continue
        src = next((bundled / s for s in sources if (bundled / s).exists()), None)
        if src is not None:
            dest.write_bytes(src.read_bytes())

    env_example = bundle_dir() / ".env.example"
    env_target = app_dir() / ".env"
    if env_example.exists() and not env_target.exists():
        env_target.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
