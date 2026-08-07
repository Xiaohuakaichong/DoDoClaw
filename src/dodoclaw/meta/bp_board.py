"""Structured BP board data for the dedicated BP UI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from dodoclaw.gsi.state import GameSnapshot
from dodoclaw.meta.base import HeroMeta
from dodoclaw.meta.draft import DraftContext, parse_draft_from_snapshot

logger = logging.getLogger(__name__)


def _pretty(name: str) -> str:
    n = (name or "").strip()
    if n.startswith("npc_dota_hero_"):
        n = n[len("npc_dota_hero_") :]
    return n.replace("_", " ").title() if n else "—"


@dataclass
class HeroChip:
    """One hero cell on the board."""

    key: str
    display: str
    hero_id: int | None = None
    win_rate: float | None = None
    picks: int = 0
    tag: str = ""  # ban_priority | recommend | avoid | neutral | counter
    note: str = ""


@dataclass
class CounterRow:
    enemy: str
    enemy_display: str
    counters: list[HeroChip] = field(default_factory=list)  # good into enemy
    weak_to: list[HeroChip] = field(default_factory=list)  # avoid into enemy


@dataclass
class PositionLane:
    position: str  # POSITION_1 .. 5
    label: str
    recommend: list[HeroChip] = field(default_factory=list)
    avoid: list[HeroChip] = field(default_factory=list)


@dataclass
class BPBoard:
    source: str = ""
    phase: str = ""
    is_draft: bool = False
    player_team: str = ""
    note: str = ""

    ally_picks: list[HeroChip] = field(default_factory=list)
    enemy_picks: list[HeroChip] = field(default_factory=list)
    ally_bans: list[HeroChip] = field(default_factory=list)
    enemy_bans: list[HeroChip] = field(default_factory=list)

    # Global meta
    ban_priority: list[HeroChip] = field(default_factory=list)  # 优先禁
    pick_hot: list[HeroChip] = field(default_factory=list)  # 高胜/高出场
    avoid_pool: list[HeroChip] = field(default_factory=list)  # 不推荐（低胜高出场等）

    counters: list[CounterRow] = field(default_factory=list)
    lanes: list[PositionLane] = field(default_factory=list)

    error: str = ""


def _chip_from_meta(hm: HeroMeta, tag: str = "", note: str = "") -> HeroChip:
    return HeroChip(
        key=hm.name or str(hm.hero_id),
        display=hm.localized_name or _pretty(hm.name),
        hero_id=hm.hero_id,
        win_rate=hm.win_rate if hm.picks else None,
        picks=hm.picks,
        tag=tag,
        note=note or (", ".join(hm.roles[:2]) if hm.roles else ""),
    )


def _chip_from_key(meta, key: str, tag: str = "") -> HeroChip:
    hm = meta.get_hero(key) if meta else None
    if hm:
        return _chip_from_meta(hm, tag=tag)
    return HeroChip(key=key, display=_pretty(key), tag=tag or "neutral")


def _taken_keys(draft: DraftContext) -> set[str]:
    keys: set[str] = set()
    for lst in (
        draft.radiant_picks,
        draft.dire_picks,
        draft.radiant_bans,
        draft.dire_bans,
    ):
        for x in lst:
            keys.add(x.lower())
            if x.startswith("npc_dota_hero_"):
                keys.add(x.replace("npc_dota_hero_", "").lower())
    return keys


def _is_taken(hm: HeroMeta, taken: set[str]) -> bool:
    names = {
        hm.name.lower() if hm.name else "",
        hm.localized_name.lower() if hm.localized_name else "",
        hm.name.replace("npc_dota_hero_", "").lower() if hm.name else "",
    }
    return bool(names & taken)


def build_bp_board(client: Any, snap: GameSnapshot, *, top_n: int = 10) -> BPBoard:
    draft = parse_draft_from_snapshot(snap)
    board = BPBoard(
        phase=draft.phase or snap.game_state or "unknown",
        is_draft=draft.is_draft,
        player_team=draft.player_team or snap.player_team or "",
    )

    try:
        meta = client.get_meta()
    except Exception as exc:
        logger.exception("meta load failed")
        board.error = f"Meta 加载失败: {exc}"
        board.source = getattr(client, "source_name", "?")
        return board

    board.source = meta.source or getattr(client, "source_name", "")
    board.note = meta.note or ""

    board.ally_picks = [_chip_from_key(meta, k, "neutral") for k in draft.ally_picks()]
    board.enemy_picks = [_chip_from_key(meta, k, "neutral") for k in draft.enemy_picks()]
    # bans: map by side roughly
    t = (draft.player_team or "").lower()
    if t in {"radiant", "team2", "2"}:
        board.ally_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.radiant_bans]
        board.enemy_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.dire_bans]
    elif t in {"dire", "team3", "3"}:
        board.ally_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.dire_bans]
        board.enemy_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.radiant_bans]
    else:
        board.ally_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.radiant_bans]
        board.enemy_bans = [_chip_from_key(meta, k, "ban_priority") for k in draft.dire_bans]

    taken = _taken_keys(draft)

    # Ban priority: high presence + solid WR, or pro ban
    try:
        bans = client.top_bans(n=top_n + 5, use_pro=True)
    except Exception:
        bans = []
    for hm in bans:
        if _is_taken(hm, taken):
            continue
        wr = f"{hm.win_rate:.0%}" if hm.picks else "—"
        board.ban_priority.append(
            _chip_from_meta(hm, "ban_priority", note=f"优先禁 · 胜率{wr}")
        )
        if len(board.ban_priority) >= top_n:
            break

    # Recommend picks: high WR with enough sample
    try:
        picks = client.top_picks(n=40, use_pro=False)
    except Exception:
        picks = list(meta.heroes.values())
        picks.sort(key=lambda h: h.picks, reverse=True)

    hot: list[HeroMeta] = []
    avoid: list[HeroMeta] = []
    for hm in picks:
        if hm.picks < 50:
            continue
        if _is_taken(hm, taken):
            continue
        if hm.win_rate >= 0.52:
            hot.append(hm)
        elif hm.win_rate <= 0.47 and hm.picks > 200:
            avoid.append(hm)

    hot.sort(key=lambda h: (h.win_rate, h.picks), reverse=True)
    avoid.sort(key=lambda h: (h.win_rate, -h.picks))  # worst first

    for hm in hot[:top_n]:
        board.pick_hot.append(
            _chip_from_meta(hm, "recommend", note=f"推荐 · {hm.win_rate:.0%} · n={hm.picks}")
        )
    for hm in avoid[:top_n]:
        board.avoid_pool.append(
            _chip_from_meta(hm, "avoid", note=f"不推荐 · {hm.win_rate:.0%} · n={hm.picks}")
        )

    # Counters vs enemy picks
    for ename in draft.enemy_picks()[:5]:
        row = CounterRow(enemy=ename, enemy_display=_pretty(ename))
        hm = meta.get_hero(ename)
        if hm:
            row.enemy_display = hm.localized_name or row.enemy_display
            try:
                counters = client.counters_for(hm.hero_id, n=6)
            except Exception:
                counters = []
            for ch, score in counters:
                if _is_taken(ch, taken):
                    continue
                row.counters.append(
                    _chip_from_meta(
                        ch,
                        "counter",
                        note=f"克制强度≈{score:.0%}",
                    )
                )
            # weak_to: invert — heroes enemy wins against hard
            try:
                matchups = client.get_matchups(hm.hero_id)
            except Exception:
                matchups = []
            weak: list[tuple[HeroMeta, float, int]] = []
            for m in matchups:
                oid = int(m.get("hero_id") or 0)
                games = int(m.get("games_played") or 0)
                wins = int(m.get("wins") or 0)
                if games < 40 or oid not in meta.heroes:
                    continue
                # high enemy winrate vs oid means oid is weak to enemy
                ewr = wins / games
                if ewr >= 0.55:
                    weak.append((meta.heroes[oid], ewr, games))
            weak.sort(key=lambda x: (x[1], x[2]), reverse=True)
            for wh, ewr, _g in weak[:5]:
                if _is_taken(wh, taken):
                    continue
                row.weak_to.append(
                    _chip_from_meta(wh, "avoid", note=f"易被压 · 敌胜{ewr:.0%}")
                )
        board.counters.append(row)

    # Lanes (STRATZ or role approx)
    pos_labels = [
        ("POSITION_1", "一号位 · 优势路"),
        ("POSITION_2", "二号位 · 中路"),
        ("POSITION_3", "三号位 · 劣势路"),
        ("POSITION_4", "四号位"),
        ("POSITION_5", "五号位"),
    ]
    for pos, label in pos_labels:
        lane = PositionLane(position=pos, label=label)
        try:
            tops = client.top_by_position(pos, n=12)
        except Exception:
            tops = []
        for hm in tops:
            if _is_taken(hm, taken):
                continue
            if hm.picks and hm.win_rate >= 0.51:
                lane.recommend.append(
                    _chip_from_meta(hm, "recommend", note=f"{hm.win_rate:.0%}")
                )
            elif hm.picks and hm.win_rate <= 0.48:
                lane.avoid.append(
                    _chip_from_meta(hm, "avoid", note=f"{hm.win_rate:.0%}")
                )
            if len(lane.recommend) >= 5 and len(lane.avoid) >= 3:
                break
        # if no avoid from split, fill avoid from lowest wr in tops
        if not lane.avoid and tops:
            low = sorted(
                [h for h in tops if h.picks and not _is_taken(h, taken)],
                key=lambda h: h.win_rate,
            )[:3]
            for hm in low:
                lane.avoid.append(_chip_from_meta(hm, "avoid", note=f"{hm.win_rate:.0%}"))
        board.lanes.append(lane)

    return board
