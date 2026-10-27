from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

GAME_STATE_ZH = {
    "DOTA_GAMERULES_STATE_INIT": "准备中",
    "DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD": "加载中",
    "DOTA_GAMERULES_STATE_HERO_SELECTION": "选人中",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME": "策略时间",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE": "展示阵容",
    "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD": "等待载入地图",
    "DOTA_GAMERULES_STATE_PRE_GAME": "出兵前",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS": "对局中",
    "DOTA_GAMERULES_STATE_POST_GAME": "对局结束",
}
TEAM_ZH = {"radiant": "天辉", "dire": "夜魇"}
# talents, map helpers and hidden slots GSI lists next to real spells
_HIDDEN_ABILITY_PREFIXES = ("special_bonus", "plus_", "generic_hidden", "ability_")


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

    # ── items / abilities by slot ───────────────────────
    def _items_in(self, *prefixes: str) -> list[dict[str, Any]]:
        return [
            i
            for i in self.items
            if str(i.get("slot") or "").startswith(prefixes)
            and (i.get("name") or "empty") != "empty"
        ]

    @property
    def inventory(self) -> list[dict[str, Any]]:
        """Main six slots (slot0-slot5)."""
        return [
            i
            for i in self._items_in("slot")
            if _as_int(str(i.get("slot"))[4:], 99) < 6
        ]

    @property
    def backpack(self) -> list[dict[str, Any]]:
        return [
            i
            for i in self._items_in("slot")
            if _as_int(str(i.get("slot"))[4:], -1) >= 6
        ]

    @property
    def stash(self) -> list[dict[str, Any]]:
        return self._items_in("stash")

    @property
    def neutral_items(self) -> list[dict[str, Any]]:
        return self._items_in("neutral")

    @property
    def has_tp(self) -> bool | None:
        """True if a usable TP is carried (scroll or Boots of Travel).

        None when the payload has no TP slot at all (can't tell)."""
        if any(str(i.get("name") or "").startswith("item_travel_boots") for i in self.inventory):
            return True
        tele = [i for i in self.items if str(i.get("slot") or "").startswith("teleport")]
        if not tele:
            return None
        return any(
            i.get("name") == "item_tpscroll" and _as_int(i.get("charges"), 1) > 0 for i in tele
        )

    @property
    def can_buyback(self) -> bool:
        return self.buyback_cooldown <= 0 and 0 < self.buyback_cost <= self.gold

    @property
    def real_abilities(self) -> list[dict[str, Any]]:
        """Hero spells only (drops talents and map / hidden helper abilities)."""
        out = []
        for a in self.abilities:
            name = str(a.get("name") or a.get("ability") or "")
            if not name or name.startswith(_HIDDEN_ABILITY_PREFIXES):
                continue
            out.append(a)
        return out

    def summary_for_llm(self) -> str:
        """Compact Chinese situation report for the coach prompt."""
        if not self.raw:
            return "当前没有收到 Dota 2 GSI 数据（可能未开对局或未配置 GSI）。"

        from dodoclaw.names import hero_key, hero_zh

        stage = GAME_STATE_ZH.get(self.game_state, self.game_state or "未知")
        day = "" if self.daytime is None else (" 白天" if self.daytime else " 夜晚")
        lines = [f"阶段: {stage}  比赛时间 {self.clock_mmss}{day}"]

        if self.hero_name:
            hk = hero_key(self.hero_name)
            team = TEAM_ZH.get(self.player_team.lower(), self.player_team) or "未知阵营"
            state = "存活" if self.hero_alive else f"阵亡，{self.respawn_seconds}s 后复活"
            hp = f"{self.hero_health}/{self.hero_max_health}"
            if self.hero_max_health:
                hp += f"({round(100 * self.hero_health / self.hero_max_health)}%)"
            lines.append(
                f"我: {hero_zh(hk)}({hk}) {self.hero_level}级 {team} {state}  "
                f"生命 {hp}  魔法 {self.hero_mana}/{self.hero_max_mana}"
            )
        lines.append(
            f"经济: {self.gold} 金 (可靠 {self.gold_reliable})  GPM {self.gpm}  XPM {self.xpm}  "
            f"KDA {self.kills}/{self.deaths}/{self.assists}  正补/反补 {self.last_hits}/{self.denies}"
        )
        if self.buyback_cost:
            if self.buyback_cooldown > 0:
                bb = f"冷却中 {self.buyback_cooldown}s"
            elif self.can_buyback:
                bb = "可用"
            else:
                bb = f"差 {self.buyback_cost - self.gold} 金"
            lines.append(f"买活: {self.buyback_cost} 金，{bb}")

        spells = [_ability_text(a) for a in self.real_abilities]
        if spells:
            lines.append("技能: " + "，".join(spells))

        def _row(label: str, items: list[dict[str, Any]]) -> None:
            if items:
                lines.append(f"{label}: " + "，".join(_item_text(i) for i in items))

        if self.items:
            inv = self.inventory
            lines.append("物品栏: " + ("，".join(_item_text(i) for i in inv) if inv else "空"))
            _row("背包", self.backpack)
            _row("中立物品", self.neutral_items)
            _row("储藏处(未带在身上)", self.stash)
            tp = self.has_tp
            if tp is not None:
                lines.append("回城卷轴: " + ("有" if tp else "没有"))

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


def _ability_text(a: dict[str, Any]) -> str:
    name = str(a.get("name") or a.get("ability") or "?")
    lvl = _as_int(a.get("level"))
    if lvl <= 0:
        return f"{name}(未学)"
    bits = [f"{lvl}级"]
    if a.get("ultimate"):
        bits.append("大招")
    if a.get("passive"):
        bits.append("被动")
    else:
        cd = _as_int(a.get("cooldown"))
        bits.append(f"冷却{cd}s" if cd > 0 else "就绪")
    return f"{name}({' '.join(bits)})"


def _item_text(i: dict[str, Any]) -> str:
    from dodoclaw.names import item_label

    text = item_label(str(i.get("name") or ""))
    extra = []
    charges = _as_int(i.get("charges"), -1)
    if charges >= 0 and "charges" in i:
        extra.append(f"{charges}层")
    cd = _as_int(i.get("cooldown"))
    if cd > 0:
        extra.append(f"冷却{cd}s")
    return f"{text}({' '.join(extra)})" if extra else text


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
    if isinstance(abilities, dict):
        for key, val in abilities.items():
            if isinstance(val, dict) and (val.get("name") or val.get("ability")):
                snap.abilities.append({**val, "slot": key})

    items = payload.get("items") or {}
    if isinstance(items, dict):
        for key, val in items.items():
            if isinstance(val, dict) and val.get("name"):
                snap.items.append({**val, "slot": key})

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
