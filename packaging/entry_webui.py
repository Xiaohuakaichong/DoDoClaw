"""PyInstaller entrypoint for the new WebView2 UI (preview build)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> None:
    from dodoclaw.paths import ensure_runtime_dirs, ensure_user_config_seeded

    ensure_user_config_seeded()
    ensure_runtime_dirs()

    frozen = getattr(sys, "frozen", False)
    log_dir = Path(sys.executable).resolve().parent / "logs" if frozen else _ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_dir / "dodoclaw.log", encoding="utf-8")],
    )

    from dodoclaw.webui.app import run_webui

    raise SystemExit(run_webui(debug="--debug" in sys.argv))


if __name__ == "__main__":
    main()
