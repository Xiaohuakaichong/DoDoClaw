"""BP / draft phase advisor using GSI draft + OpenDota / STRATZ meta."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from dodoclaw.gsi.state import GameSnapshot
from dodoclaw.meta.base import HeroMeta

logger = logging.getLogger(__name__)

DRAFT_STATES = {
    "DOTA_GAMERULES_STATE_HERO_SELECTION",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE",
    "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD",
}


@dataclass
class DraftContext:
    phase: str = ""
    is_draft: bool = False
    radiant_picks: list[str] = field(default_factory=list)
    dire_picks: list[str] = field(default_factory=list)
    radiant_bans: list[str] = field(default_factory=list)
    dire_bans: list[str] = field(default_factory=list)
    player_team: str = ""
    raw_draft: dict[str, Any] = field(default_factory=dict)

    def ally_picks(self) -> list[str]:
        t = (self.player_team or "").lower()
        if t in {"radiant", "team2", "2"}:
            return list(self.radiant_picks)
        if t in {"dire", "team3", "3"}:
            return list(self.dire_picks)
        return list(self.radiant_picks)

    def enemy_picks(self) -> list[str]:
        t = (self.player_team or "").lower()
        if t in {"radiant", "team2", "2"}:
            return list(self.dire_picks)
        if t in {"dire", "team3", "3"}:
            return list(self.radiant_picks)
        return list(self.dire_picks)

    def summary_text(self) -> str:
        if not self.is_draft and not (self.radiant_picks or self.dire_picks):
            return "当前不在 BP/选人阶段（或 GSI 尚未推送 draft）。"
        return "\n".join(
            [
                f"阶段: {self.phase or 'unknown'}",
                f"我方: {self.player_team or '未知'}",
                f"天辉 pick: {', '.join(self.radiant_picks) or '—'}",
                f"天辉 ban: {', '.join(self.radiant_bans) or '—'}",
                f"夜魇 pick: {', '.join(self.dire_picks) or '—'}",
                f"夜魇 ban: {', '.join(self.dire_bans) or '—'}",
            ]
        )


def _hero_label(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        for k in ("name", "hero", "hero_name", "id"):
            if val.get(k) is not None:
                return str(val.get(k))
        return ""
    return str(val)


def parse_draft_from_snapshot(snap: GameSnapshot) -> DraftContext:
    ctx = DraftContext(player_team=snap.player_team or "")
    gs = snap.game_state or ""
    if gs in DRAFT_STATES or "HERO_SELECTION" in gs or "STRATEGY" in gs:
        ctx.is_draft = True
        ctx.phase = gs
    elif gs == "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS":
        ctx.phase = "in_game"
        ctx.is_draft = False
    else:
        ctx.phase = gs or "unknown"

    draft = (snap.raw or {}).get("draft") or {}
    ctx.raw_draft = draft if isinstance(draft, dict) else {}

    for team_key, side in (
        ("team2", "radiant"),
        ("team3", "dire"),
        ("radiant", "radiant"),
        ("dire", "dire"),
    ):
        block = draft.get(team_key)
        if not isinstance(block, dict):
            continue
        picks: list[str] = []
        bans: list[str] = []
        for k, v in block.items():
            label = _hero_label(v)
            if not label or label in {"0", "null", "None"}:
                continue
            kl = k.lower()
            if "ban" in kl:
                bans.append(label)
            elif "pick" in kl or "hero" in kl:
                picks.append(label)
        if side == "radiant":
            ctx.radiant_picks = picks or ctx.radiant_picks
            ctx.radiant_bans = bans or ctx.radiant_bans
        else:
            ctx.dire_picks = picks or ctx.dire_picks
            ctx.dire_bans = bans or ctx.dire_bans

    if not ctx.radiant_picks and not ctx.dire_picks:
        for k, v in draft.items():
            if not isinstance(k, str):
                continue
            label = _hero_label(v)
            if not label:
                continue
            kl = k.lower()
            if "radiant" in kl or "team2" in kl:
                (ctx.radiant_bans if "ban" in kl else ctx.radiant_picks).append(label)
            elif "dire" in kl or "team3" in kl:
                (ctx.dire_bans if "ban" in kl else ctx.dire_picks).append(label)

    if ctx.radiant_picks or ctx.dire_picks or ctx.radiant_bans or ctx.dire_bans:
        ctx.is_draft = True or ctx.is_draft

    return ctx


class DraftAdvisor:
    def __init__(self, client: Any) -> None:
        self.client = client

    @property
    def source_name(self) -> str:
        return getattr(self.client, "source_name", type(self.client).__name__)

    def build_advice(self, snap: GameSnapshot, *, top_n: int = 8) -> str:
        draft = parse_draft_from_snapshot(snap)
        try:
            meta = self.client.get_meta()
        except Exception as exc:
            logger.exception("meta load failed")
            return (
                f"{draft.summary_text()}\n"
                f"（Meta 数据暂时不可用: {exc}。仍可按通用 BP 原则建议。）"
            )

        src = meta.source or self.source_name
        lines = [
            f"【BP / 选人指导 · 数据源 {src.upper()}】",
            meta.note or "",
            draft.summary_text(),
            "",
            "— 优先关注 / 高 ban 价值（统计向）—",
        ]
        for h in self.client.top_bans(n=top_n, use_pro=True):
            lines.append(
                f"  · {h.localized_name}  出场={h.picks} 胜率={h.win_rate:.1%}"
                + (f" pro_ban={h.pro_ban}" if h.pro_ban else "")
            )

        lines.append("")
        lines.append("— 高频 Pick —")
        for h in self.client.top_picks(n=top_n, use_pro=False):
            roles = ",".join(h.roles[:3]) if h.roles else "-"
            lines.append(
                f"  · {h.localized_name}  pick≈{h.picks} 胜率={h.win_rate:.1%} 定位={roles}"
            )

        # STRATZ position meta
        if getattr(meta, "by_position", None):
            lines.append("")
            lines.append("— 分路热门（STRATZ position）—")
            pos_labels = {
                "POSITION_1": "一号位/优势路",
                "POSITION_2": "中路",
                "POSITION_3": "三号位/劣势路",
                "POSITION_4": "四号位",
                "POSITION_5": "五号位",
            }
            for pos, label in pos_labels.items():
                tops = self.client.top_by_position(pos, n=5)
                if not tops:
                    continue
                names = ", ".join(
                    f"{h.localized_name}({h.win_rate:.0%}/{h.picks})" for h in tops[:5]
                )
                lines.append(f"  · {label}: {names}")

        enemy = draft.enemy_picks()
        if enemy:
            lines.append("")
            lines.append("— 针对敌方已选的克制方向 —")
            for ename in enemy[:5]:
                hm = meta.get_hero(ename)
                if not hm:
                    lines.append(f"  · {ename}: 未匹配英雄 ID")
                    continue
                counters = self.client.counters_for(hm.hero_id, n=5)
                if not counters:
                    lines.append(f"  · 克 {hm.localized_name}: 对位样本不足")
                    continue
                names = ", ".join(
                    f"{c.localized_name}({score:.0%})" for c, score in counters[:5]
                )
                lines.append(f"  · 克 {hm.localized_name}: {names}")

        lines.append("")
        if src == "stratz":
            lines.append("数据来源: STRATZ（用户自备 Token）。请结合熟练度与版本变化。")
        else:
            lines.append(
                "数据来源: OpenDota。若需分路精细 Meta，可在设置切换 STRATZ 并填写 Token。"
            )
        return "\n".join(lines)

    def meta_brief(self, n: int = 10) -> str:
        try:
            bans = self.client.top_bans(n=n, use_pro=True)
            picks = self.client.top_picks(n=n, use_pro=False)
        except Exception as exc:
            return f"Meta 不可用: {exc}"
        ban_s = ", ".join(h.localized_name for h in bans)
        pick_s = ", ".join(h.localized_name for h in picks)
        return f"[{self.source_name}] 热门Ban: {ban_s}\n热门Pick: {pick_s}"
