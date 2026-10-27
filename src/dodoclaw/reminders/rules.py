from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dodoclaw.gsi.objectives import MatchEvents
from dodoclaw.gsi.state import GameSnapshot
from dodoclaw.reminders import schedule as sch


@dataclass(frozen=True)
class ReminderHit:
    key: str
    message: str
    priority: int = 0


RuleFn = Callable[[GameSnapshot, GameSnapshot | None], list[ReminderHit]]


def _prev_clock(snapshot: GameSnapshot, prev: GameSnapshot | None) -> int | None:
    """Previous packet's clock, only when it belongs to the same running match."""
    if prev is None or not prev.in_game or prev.match_id != snapshot.match_id:
        return None
    return prev.clock_time


def _in_fire_window(
    clock: int,
    fire_at: int,
    width: int = 1,
    prev_clock: int | None = None,
) -> bool:
    """Fire inside the 1 s window, or when the clock jumped over ``fire_at``.

    GSI packets don't land on every game second (throttle, alt-tab, a stalled
    client); with only an exact window a skipped second meant a lost reminder.
    """
    if fire_at <= clock <= fire_at + width:
        return True
    return (
        prev_clock is not None
        and prev_clock < fire_at <= clock <= fire_at + sch.CATCHUP_SEC
    )


def _window_hits(
    snapshot: GameSnapshot,
    prev: GameSnapshot | None,
    windows: list[sch.WarnWindow],
    priority: int,
) -> list[ReminderHit]:
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t, pt = snapshot.clock_time, _prev_clock(snapshot, prev)
    for w in windows:
        if _in_fire_window(t, w.fire_at, prev_clock=pt):
            key = f"{w.family}:{w.spawn_sec}"
            return [ReminderHit(key=key, message=w.message, priority=priority)]
    return []


def water_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Water runes at 2:00 & 4:00; warn 15s prior. domain/reminder-budget.md."""
    return _window_hits(snapshot, prev, sch.water_windows(), priority=5)


def power_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Power runes from 6:00 every 2 min; warn 15s. domain/reminder-budget.md."""
    return _window_hits(snapshot, prev, sch.power_windows(), priority=5)


def bounty_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Bounty every 3 min from 0:00, skip 0:00; warn 20s from 3:00."""
    return _window_hits(snapshot, prev, sch.bounty_windows(), priority=3)


def lotus_pool_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Lotus: at the mark from 6:00 every 6 min. Exact wording from reminder-budget.md."""
    wins = [
        sch.WarnWindow("lotus", m, sch.LOTUS_WARN_SEC, sch.LOTUS_MSG) for m in sch.lotus_marks()
    ]
    return _window_hits(snapshot, prev, wins, priority=4)


def shrine_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """智慧神龛 7:00 then every 7 min; warn 15s."""
    return _window_hits(snapshot, prev, sch.shrine_windows(), priority=4)


def tormentor_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """痛苦魔方 first spawn 15:00; warn 30s."""
    return _window_hits(snapshot, prev, sch.tormentor_windows(), priority=5)


def buyback_ready_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Late game: buyback just became available / gold just dropped under the price
    (usually a big purchase) / dead with buyback up. Early deaths are not a buyback
    question, so nothing before 25:00 except a buyback cooldown running out."""
    if not snapshot.in_game:
        return []
    t = snapshot.clock_time
    cost = snapshot.buyback_cost
    late = t >= sch.BUYBACK_LATE_SEC
    if (
        prev is not None
        and snapshot.hero_alive
        and snapshot.can_buyback
        and not prev.can_buyback
        and (late or prev.buyback_cooldown > 0)
    ):
        return [
            ReminderHit(key=f"buyback_ready:{t // 300}", message=sch.BUYBACK_READY_MSG, priority=8)
        ]
    if not late or snapshot.buyback_cooldown > 0 or cost <= 0:
        return []
    if not snapshot.hero_alive and snapshot.gold >= cost:
        return [
            ReminderHit(
                key=f"buyback_while_dead:{snapshot.deaths}",  # once per death
                message=sch.BUYBACK_DEAD_MSG,
                priority=9,
            )
        ]
    if (
        snapshot.hero_alive
        and prev is not None
        and prev.hero_alive
        and prev.gold >= cost > snapshot.gold
    ):
        return [
            ReminderHit(
                key=f"buyback_short:{t // 300}",
                message=sch.BUYBACK_SHORT_MSG,
                priority=6,
            )
        ]
    return []


def low_health_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    if not snapshot.in_game or not snapshot.hero_alive:
        return []
    if snapshot.hero_max_health <= 0:
        return []
    ratio = snapshot.hero_health / snapshot.hero_max_health
    if ratio <= 0.2:
        return [
            ReminderHit(
                key=f"low_hp:{snapshot.clock_time // 20}",
                message="血量危险，考虑撤退、吃树或回家。",
                priority=7,
            )
        ]
    return []


def ult_ready_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    if not snapshot.in_game or not snapshot.hero_alive:
        return []
    for a in snapshot.abilities:
        if not a.get("ultimate"):
            continue
        cd = a.get("cooldown", 0) or 0
        can_cast = a.get("can_cast", None)
        name = a.get("name") or "大招"
        if (can_cast is True) or (cd == 0 and a.get("level", 0) > 0):
            if prev:
                prev_ult = next(
                    (x for x in prev.abilities if x.get("ultimate")),
                    None,
                )
                if prev_ult and (prev_ult.get("cooldown", 0) or 0) > 0:
                    return [
                        ReminderHit(
                            key=f"ult_ready:{name}:{snapshot.clock_time}",
                            message=f"{name} 已就绪。",
                            priority=4,
                        )
                    ]
    return []


class ObjectiveRule:
    """Roshan respawn window and Aegis expiry, timed from GSI ``events``.

    Pass the service's shared ``MatchEvents`` (fed on every packet); without
    one the rule keeps its own and feeds it from each snapshot.
    """

    __name__ = "objective_rule"

    def __init__(self, events: MatchEvents | None = None) -> None:
        self._own = events is None
        self.events = events if events is not None else MatchEvents()

    def __call__(self, snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
        if self._own:
            self.events.ingest(snapshot.raw)
        if not snapshot.in_game or snapshot.clock_time < 0:
            return []
        if snapshot.match_id and self.events.match_id and snapshot.match_id != self.events.match_id:
            return []  # tracker still holds the previous match
        t, pt = snapshot.clock_time, _prev_clock(snapshot, prev)
        hits: list[ReminderHit] = []
        rosh = self.events.roshan_killed_at
        if rosh is not None and _in_fire_window(t, sch.roshan_warn_at(rosh), prev_clock=pt):
            hits.append(ReminderHit(key=f"roshan:{rosh}", message=sch.ROSHAN_MSG, priority=9))
        aegis = self.events.aegis_at
        if aegis is not None and _in_fire_window(t, sch.aegis_warn_at(aegis), prev_clock=pt):
            hits.append(ReminderHit(key=f"aegis:{aegis}", message=sch.AEGIS_MSG, priority=9))
        return hits


class NoTpRule:
    """No TP scroll (or Boots of Travel) at the 10:00 / 20:00 checks → one nag each."""

    __name__ = "no_tp_rule"

    def __init__(self) -> None:
        self._match: str | None = None
        self._done: set[int] = set()

    def __call__(self, snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
        if snapshot.match_id != self._match:
            self._match, self._done = snapshot.match_id, set()
        if not snapshot.in_game:
            return []
        t = snapshot.clock_time
        for mark in sch.TP_CHECK_SEC:
            if mark in self._done or not mark <= t <= mark + sch.TP_CHECK_WINDOW_SEC:
                continue
            has = snapshot.has_tp
            if not snapshot.hero_alive or has is None:
                return []  # can't judge right now; try again later in the window
            self._done.add(mark)
            if not has:
                return [ReminderHit(key=f"no_tp:{mark}", message=sch.TP_MSG, priority=4)]
        return []


DEFAULT_RULES: list[RuleFn] = [
    water_rune_rule,
    power_rune_rule,
    bounty_rune_rule,
    lotus_pool_rule,
    shrine_rule,
    tormentor_rule,
    buyback_ready_rule,
    low_health_rule,
]


def default_rules(events: MatchEvents | None = None) -> list[RuleFn]:
    """Stateless defaults plus fresh stateful rules (one set per engine)."""
    return [*DEFAULT_RULES, ObjectiveRule(events), NoTpRule()]
