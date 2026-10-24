"""Settings-page options (reminders, voice, overlay) persisted in config/settings.yaml.

Only the top-level ``ui:`` block of settings.yaml is (re)written; every other
line and comment in that file is left untouched. Nothing here reads or writes
``.env``.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml

BUDGET_CAP = 30  # suggested per-game ceiling; the default config stays under it, but users may exceed it
OVER_CAP_HINT = f"超过建议的 {BUDGET_CAP} 条，对局中可能比较吵"
LEAD_MIN, LEAD_MAX = 5, 60
POSITIONS = (1, 2, 3, 4, 5)

# key -> (estimated announcements per 40-min game, default lead seconds or None)
# Counts follow domain/reminder-budget.md (patch 7.41f baseline).
REMINDERS: dict[str, tuple[int, int | None]] = {
    # Counts follow domain/reminder-budget.md (7.41f + 2026-10-24 lotus update).
    # pos3 16→20 / pos4·5 22→26 with lotus≈4; pos1/2 unchanged.
    "bounty": (6, 20),   # 赏金符 — warn 20s; default on for pos 4/5
    "runes": (10, 15),   # 水符 2 + 强化符 8 — default on for pos 2
    "lotus": (4, None),  # 莲花池 — at the mark, no early warn; default pos 3/4/5
    "shrine": (5, 15),   # 智慧神龛
    "cube": (2, 30),     # 痛苦魔方
    "roshan": (2, 30),   # 肉山复活
    "aegis": (2, 60),    # 不朽盾（剩 1 分钟）
    "tp": (2, None),     # 没带回城卷轴（固定时间检查）
    "buyback": (3, None),  # 后期买活（状态变化）
    "lowhp": (0, None),  # 低血量 · 大招就绪 — default off, not counted
}

# Rows the reminder engine has no rule for yet: shown greyed out as 即将上线,
# always off, cannot be switched on, and not counted in the per-game budget.
PENDING = frozenset({"shrine", "cube", "roshan", "aegis", "tp"})
PENDING_MSG = "这条提醒还在做"

# reminder engine key family -> settings row
FAMILY_TO_ROW = {
    "bounty_rune": "bounty",
    "power_rune": "runes",
    "water_rune": "runes",
    "lotus": "lotus",
    "shrine": "shrine",
    "cube": "cube",
    "roshan": "roshan",
    "aegis": "aegis",
    "tp": "tp",
    "no_tp": "tp",
    "buyback_ready": "buyback",
    "buyback_while_dead": "buyback",
    "low_hp": "lowhp",
    "ult_ready": "lowhp",
}


def default_on(row: str, positions: list[int] | tuple[int, ...]) -> bool:
    pos = set(positions or ())
    if row in PENDING:
        return False
    if row == "bounty":
        return bool(pos & {4, 5})
    if row == "runes":
        return 2 in pos
    if row == "lotus":
        return bool(pos & {3, 4, 5})
    if row == "lowhp":
        return False
    return True


def defaults(positions: list[int] | None = None) -> dict[str, Any]:
    positions = list(positions or [1])
    return {
        "positions": positions,
        "reminders": {
            k: {"on": default_on(k, positions), "lead": lead}
            for k, (_n, lead) in REMINDERS.items()
        },
        "overrides": [],          # rows the user toggled by hand; position changes keep them
        "voice_ask": None,        # None = derive from current speech-recognition backend
        "stt_mode": None,         # legacy (local | cloud); read once to pick voice.stt_backend
        "tts_on": None,           # None = derive from the configured TTS backend
        "overlay_opacity": 88,
        "auto_overlay": True,
        "reduce_motion": False,
    }


def budget(rem: dict[str, dict[str, Any]]) -> int:
    return sum(
        REMINDERS[k][0]
        for k, v in rem.items()
        if k in REMINDERS and k not in PENDING and v.get("on")
    )


def merge(saved: dict[str, Any] | None) -> dict[str, Any]:
    """Defaults overlaid with whatever valid values were saved."""
    saved = saved if isinstance(saved, dict) else {}
    pos = [p for p in (saved.get("positions") or []) if p in POSITIONS] or [1]
    out = defaults(pos)
    for k, v in (saved.get("reminders") or {}).items():
        if k in out["reminders"] and isinstance(v, dict):
            if "on" in v and k not in PENDING:
                out["reminders"][k]["on"] = bool(v["on"])
            # lead times are not user-editable until the engine supports them
    out["overrides"] = [k for k in (saved.get("overrides") or []) if k in REMINDERS and k not in PENDING]
    for k in ("voice_ask", "tts_on", "auto_overlay", "reduce_motion"):
        if saved.get(k) is not None:
            out[k] = bool(saved[k])
    if saved.get("stt_mode") in ("local", "cloud"):
        out["stt_mode"] = saved["stt_mode"]
    if saved.get("overlay_opacity") is not None:
        try:
            out["overlay_opacity"] = max(40, min(100, int(saved["overlay_opacity"])))
        except (TypeError, ValueError):
            pass
    return out


def clamp_lead(v: Any) -> int:
    try:
        n = int(round(float(v) / 5.0) * 5)
    except (TypeError, ValueError):
        n = 15
    return max(LEAD_MIN, min(LEAD_MAX, n))


def apply_positions(cur: dict[str, Any], positions: list[int]) -> dict[str, Any]:
    """Reset default on/off for rows the user has not toggled by hand."""
    out = copy.deepcopy(cur)
    pos = sorted({int(p) for p in positions if int(p) in POSITIONS}) or [1]
    out["positions"] = pos
    for k in REMINDERS:
        if k not in out["overrides"] or k in PENDING:
            out["reminders"][k]["on"] = default_on(k, pos)
    return out


def toggle_reminder(cur: dict[str, Any], row: str, on: bool) -> tuple[dict[str, Any], str]:
    """Returns (new_settings, error_zh). Going over BUDGET_CAP is allowed (UI warns)."""
    if row not in REMINDERS:
        return cur, "没有这项提醒"
    if row in PENDING:
        return cur, PENDING_MSG
    out = copy.deepcopy(cur)
    out["reminders"][row]["on"] = bool(on)
    if row not in out["overrides"]:
        out["overrides"].append(row)
    return out, ""


# ── settings.yaml I/O ────────────────────────────────
_TOP_KEY = re.compile(r"^ui\s*:")


def load(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        data = {}
    return merge(data.get("ui") if isinstance(data, dict) else None)


def save(path: Path, settings: dict[str, Any]) -> None:
    """Replace (or append) only the top-level ``ui:`` block of settings.yaml."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    block = yaml.safe_dump({"ui": settings}, allow_unicode=True, sort_keys=False).rstrip("\n")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if _TOP_KEY.match(ln)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["# 设置页里的选项（DoDoClaw 自动写入，可以手动改）", *block.splitlines()]
    else:
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
            end += 1
        # keep trailing blank lines that separate the next block
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[start:end] = block.splitlines()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
