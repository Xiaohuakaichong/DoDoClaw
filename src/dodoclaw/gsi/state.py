from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GameSnapshot:
    """Normalized view of the latest GSI payload for coach / reminders."""

    updated_at: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    map_name: str = ""
    game_state: str = ""  # DOTA_GAMERULES_STATE_*
    clock_time: int = 0  # seconds; can be negative during pregame
    daytime: bool | None = None
    match_id: str = ""

    player_name: str = ""
    player_team: str = ""  # radiant / dire
    gold: int = 0
    gold_reliable: int = 0
    gold_unreliable: int = 0
    gpm: int = 0
    xpm: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    last_hits: int = 0
    denies: int = 0
    buyback_cost: int = 0
    buyback_cooldown: int = 0

    hero_name: str = ""
    hero_level: int = 0
    hero_alive: bool = True
    hero_health: int = 0
    hero_max_health: int = 0
    hero_mana: int = 0
    hero_max_mana: int = 0
    hero_xpos: int | None = None
    hero_ypos: int | None = None
    respawn_seconds: int = 0

    abilities: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def in_game(self) -> bool:
        return self.game_state in {
            "DOTA_GAMERULES_STATE_PRE_GAME",
            "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
        }

    @property
    def clock_mmss(self) -> str:
        t = int(self.clock_time)
        sign = "-" if t < 0 else ""
        t = abs(t)
        return f"{sign}{t // 60:02d}:{t % 60:02d}"

    def summary_for_llm(self) -> str:
        if not self.raw:
            return "当前没有收到 Dota 2 GSI 数据（可能未开对局或未配置 GSI）。"

        lines = [
            f"地图: {self.map_name or 'unknown'}",
            f"阶段: {self.game_state or 'unknown'}",
            f"比赛时间: {self.clock_mmss} ({self.clock_time}s)",
            f"昼夜: {self.daytime}",
            f"玩家: {self.player_name} / {self.player_team}",
            f"英雄: {self.hero_name} Lv{self.hero_level} "
            f"{'存活' if self.hero_alive else f'阵亡(复活{self.respawn_seconds}s)'}",
            f"生命: {self.hero_health}/{self.hero_max_health}  魔法: {self.hero_mana}/{self.hero_max_mana}",
            f"经济: 总金 {self.gold} (可靠 {self.gold_reliable} / 不可靠 {self.gold_unreliable}) "
            f"GPM {self.gpm} XPM {self.xpm}",
            f"KDA: {self.kills}/{self.deaths}/{self.assists}  LH/DN: {self.last_hits}/{self.denies}",
            f"买活: 花费 {self.buyback_cost}  CD {self.buyback_cooldown}s",
        ]

        if self.abilities:
            ab = []
            for a in self.abilities:
                name = a.get("name") or a.get("ability") or "?"
                cd = a.get("cooldown", 0)
                ul = a.get("ultimate", False)
                ab.append(f"{name}(cd={cd}{' ult' if ul else ''})")
            lines.append("技能: " + ", ".join(ab))

        if self.items:
            it = []
            for i in self.items:
                name = i.get("name") or "?"
                if name and name != "empty":
                    it.append(name)
            lines.append("物品: " + (", ".join(it) if it else "无"))

        draft = self.raw.get("draft") if self.raw else None
        if isinstance(draft, dict) and draft:
            lines.append(f"Draft 原始字段数: {len(draft)}（详见 BP 指导模块）")

        return "\n".join(lines)

    @property
    def is_draft_phase(self) -> bool:
        gs = self.game_state or ""
        return (
            "HERO_SELECTION" in gs
            or "STRATEGY" in gs
            or gs
            in {
                "DOTA_GAMERULES_STATE_HERO_SELECTION",
                "DOTA_GAMERULES_STATE_STRATEGY_TIME",
                "DOTA_GAMERULES_STATE_TEAM_SHOWCASE",
            }
        )


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def parse_gsi_payload(payload: dict[str, Any]) -> GameSnapshot:
    snap = GameSnapshot(updated_at=time.time(), raw=payload)

    m = payload.get("map") or {}
    snap.map_name = str(m.get("name") or "")
    snap.game_state = str(m.get("game_state") or "")
    snap.clock_time = _as_int(m.get("clock_time"))
    if "daytime" in m:
        snap.daytime = bool(m.get("daytime"))
    snap.match_id = str(m.get("matchid") or "")

    p = payload.get("player") or {}
    # player may be nested under team slots in some modes; keep simple single-player path
    if "team2" in p or "team3" in p:
        # spectator / multi — leave defaults
        pass
    else:
        snap.player_name = str(p.get("name") or "")
        snap.player_team = str(p.get("team_name") or p.get("team") or "")
        snap.gold = _as_int(p.get("gold"))
        snap.gold_reliable = _as_int(p.get("gold_reliable"))
        snap.gold_unreliable = _as_int(p.get("gold_unreliable"))
        snap.gpm = _as_int(p.get("gpm"))
        snap.xpm = _as_int(p.get("xpm"))
        snap.kills = _as_int(p.get("kills"))
        snap.deaths = _as_int(p.get("deaths"))
        snap.assists = _as_int(p.get("assists"))
        snap.last_hits = _as_int(p.get("last_hits"))
        snap.denies = _as_int(p.get("denies"))
        snap.buyback_cost = _as_int(p.get("buyback_cost"))
        snap.buyback_cooldown = _as_int(p.get("buyback_cooldown"))

    h = payload.get("hero") or {}
    if "team2" not in h and "team3" not in h:
        snap.hero_name = str(h.get("name") or "")
        snap.hero_level = _as_int(h.get("level"))
        snap.hero_alive = bool(h.get("alive", True)) if "alive" in h else True
        snap.hero_health = _as_int(h.get("health"))
        snap.hero_max_health = _as_int(h.get("max_health"))
        snap.hero_mana = _as_int(h.get("mana"))
        snap.hero_max_mana = _as_int(h.get("max_mana"))
        if "xpos" in h:
            snap.hero_xpos = _as_int(h.get("xpos"))
        if "ypos" in h:
            snap.hero_ypos = _as_int(h.get("ypos"))
        snap.respawn_seconds = _as_int(h.get("respawn_seconds"))

    abilities = payload.get("abilities") or {}
    for key, val in abilities.items():
        if isinstance(val, dict) and (val.get("name") or val.get("ability")):
            snap.abilities.append(val)

    items = payload.get("items") or {}
    for key, val in items.items():
        if isinstance(val, dict) and val.get("name"):
            snap.items.append(val)

    return snap


class GameStateStore:
    """Thread-safe latest snapshot holder."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = GameSnapshot()
        self._update_count = 0

    def update(self, payload: dict[str, Any]) -> GameSnapshot:
        snap = parse_gsi_payload(payload)
        with self._lock:
            self._snapshot = snap
            self._update_count += 1
            return snap

    def get(self) -> GameSnapshot:
        with self._lock:
            return self._snapshot

    @property
    def update_count(self) -> int:
        with self._lock:
            return self._update_count
