from __future__ import annotations

import os
import shutil
from pathlib import Path

from dodoclaw.paths import config_dir


def resolve_dota_cfg_target() -> Path | None:
    """Best-effort locate Steam Dota 2 GSI cfg folder on Windows."""
    steam_paths = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration"),
        Path(r"D:\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration"),
        Path(r"E:\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration"),
        Path(r"D:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\cfg\gamestate_integration"),
    ]
    for p in steam_paths:
        if p.parent.exists():
            return p

    steam = os.environ.get("STEAM_PATH")
    if steam:
        return (
            Path(steam)
            / "steamapps"
            / "common"
            / "dota 2 beta"
            / "game"
            / "dota"
            / "cfg"
            / "gamestate_integration"
        )
    return None


def install_gsi_cfg() -> tuple[bool, str, Path | None]:
    """
    Install GSI cfg into Dota 2.
    Returns (ok, message, dest_path_or_none).
    """
    src = config_dir() / "gamestate_integration_dodoclaw.cfg"
    if not src.exists():
        return False, f"找不到配置模板: {src}", None

    target_dir = resolve_dota_cfg_target()
    if target_dir is None:
        return (
            False,
            "未自动找到 Dota 2 目录。请设置环境变量 STEAM_PATH，或手动复制 config 下的 cfg 到 "
            "<Steam>\\steamapps\\common\\dota 2 beta\\game\\dota\\cfg\\gamestate_integration\\",
            None,
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / src.name
    shutil.copy2(src, dest)
    return (
        True,
        f"GSI 已安装到:\n{dest}\n\n请完全重启 Dota 2 后再进对局。",
        dest,
    )
