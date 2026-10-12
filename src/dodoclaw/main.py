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


def cmd_run_webui(debug: bool = False) -> int:
    from dodoclaw.webui.app import run_webui

    return run_webui(debug=debug)


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


def cmd_knowledge_sync(force: bool = True) -> int:
    from dodoclaw.knowledge.base import KnowledgeBase

    yaml_cfg = get_settings().load_yaml()
    kb_cfg = yaml_cfg.get("knowledge") or {}
    kb = KnowledgeBase(
        language=str(kb_cfg.get("language") or "schinese"),
        patch_last_n=int(kb_cfg.get("patch_last_n") or 3),
        ttl_sec=int(kb_cfg.get("ttl_sec") or 24 * 3600),
    )
    console.print("[cyan]正在同步英雄机制（OpenDota）+ 官方补丁（Valve）…[/cyan]")
    try:
        stats = kb.sync(force=force)
    except Exception as exc:
        console.print(f"[red]同步失败: {exc}[/red]")
        return 1
    console.print(f"[green]完成[/green] {stats}")
    console.print(kb.stats())
    return 0


def cmd_knowledge_stats() -> int:
    from dodoclaw.knowledge.base import KnowledgeBase

    kb = KnowledgeBase()
    kb.load()
    console.print(kb.stats())
    return 0


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
    w = sub.add_parser("webui", help="新界面原型（pywebview / WebView2）")
    w.add_argument("--debug", action="store_true", help="打开 WebView 开发者工具")
    sub.add_parser("install-gsi", help="安装 Dota 2 GSI 配置文件")
    sub.add_parser("health", help="检查本地 GSI /health")
    sub.add_parser(
        "knowledge-sync",
        help="同步知识库：英雄技能机制 + 最近官方补丁",
    )
    sub.add_parser("knowledge-stats", help="查看本地知识库统计")
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
    if cmd == "webui":
        raise SystemExit(cmd_run_webui(debug=getattr(args, "debug", False)))
    if cmd == "cli":
        raise SystemExit(cmd_run_cli())
    if cmd == "install-gsi":
        raise SystemExit(cmd_install_gsi_cfg())
    if cmd == "health":
        raise SystemExit(cmd_health())
    if cmd == "knowledge-sync":
        raise SystemExit(cmd_knowledge_sync(force=True))
    if cmd == "knowledge-stats":
        raise SystemExit(cmd_knowledge_stats())
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
