from __future__ import annotations

import argparse
import logging
import sys

from rich.console import Console

from dodoclaw import __version__
from dodoclaw.config import get_settings
from dodoclaw.gsi_install import install_gsi_cfg
from dodoclaw.paths import ensure_runtime_dirs, ensure_user_config_seeded

console = Console()


def setup_logging(level: str = "INFO") -> None:
    ensure_user_config_seeded()
    ensure_runtime_dirs()
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_install_gsi_cfg() -> int:
    ok, msg, _dest = install_gsi_cfg()
    if ok:
        console.print(f"[green]{msg}[/green]")
        return 0
    console.print(f"[yellow]{msg}[/yellow]")
    return 2


def cmd_run_cli() -> int:
    from dodoclaw.app import DoDoClawApp

    DoDoClawApp().run_interactive()
    return 0


def cmd_run_gui() -> int:
    from dodoclaw.gui.app import run_gui

    return run_gui()


def cmd_health() -> int:
    import httpx

    settings = get_settings()
    url = f"http://{settings.gsi_host}:{settings.gsi_port}/health"
    try:
        r = httpx.get(url, timeout=2.0)
        console.print(r.json())
        return 0 if r.status_code == 200 else 1
    except Exception as exc:
        console.print(f"[red]无法连接 GSI: {exc}[/red]")
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dodoclaw",
        description="DoDoClaw — Dota 2 voice coach assistant",
    )
    p.add_argument("--version", action="version", version=f"DoDoClaw {__version__}")
    p.add_argument("--log-level", default=None, help="DEBUG|INFO|WARNING|ERROR")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("gui", help="启动桌面 App（默认，适合社区分发）")
    sub.add_parser("run", help="同 gui")
    sub.add_parser("cli", help="终端交互模式")
    sub.add_parser("install-gsi", help="安装 Dota 2 GSI 配置文件")
    sub.add_parser("health", help="检查本地 GSI /health")
    return p


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    yaml_cfg = settings.load_yaml()
    log_level = args.log_level or (yaml_cfg.get("logging") or {}).get("level") or "INFO"
    setup_logging(str(log_level))

    # Default to GUI for double-click / community usage
    cmd = args.command or "gui"
    if cmd in {"gui", "run"}:
        raise SystemExit(cmd_run_gui())
    if cmd == "cli":
        raise SystemExit(cmd_run_cli())
    if cmd == "install-gsi":
        raise SystemExit(cmd_install_gsi_cfg())
    if cmd == "health":
        raise SystemExit(cmd_health())
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
