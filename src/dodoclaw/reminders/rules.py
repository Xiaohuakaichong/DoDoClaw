from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dodoclaw.gsi.state import GameSnapshot
from dodoclaw.reminders import schedule as sch


@dataclass(frozen=True)
class ReminderHit:
    key: str
    message: str
    priority: int = 0


RuleFn = Callable[[GameSnapshot, GameSnapshot | None], list[ReminderHit]]


def _in_fire_window(clock: int, fire_at: int, width: int = 1) -> bool:
    return fire_at <= clock <= fire_at + width


def water_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Water runes at 2:00 & 4:00; warn 15s prior. domain/reminder-budget.md."""
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t = snapshot.clock_time
    for w in sch.water_windows():
        if _in_fire_window(t, w.fire_at):
            return [
                ReminderHit(
                    key=f"water_rune:{w.spawn_sec}",
                    message=w.message,
                    priority=5,
                )
            ]
    return []


def power_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Power runes from 6:00 every 2 min; warn 15s. domain/reminder-budget.md."""
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t = snapshot.clock_time
    for w in sch.power_windows():
        if _in_fire_window(t, w.fire_at):
            return [
                ReminderHit(
                    key=f"power_rune:{w.spawn_sec}",
                    message=w.message,
                    priority=5,
                )
            ]
    return []


def bounty_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Bounty every 3 min from 0:00, skip 0:00; warn 20s from 3:00."""
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t = snapshot.clock_time
    for w in sch.bounty_windows():
        if _in_fire_window(t, w.fire_at):
            return [
                ReminderHit(
                    key=f"bounty_rune:{w.spawn_sec}",
                    message=w.message,
                    priority=3,
                )
            ]
    return []


def lotus_pool_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Lotus: at the mark from 6:00 every 6 min. Exact wording from reminder-budget.md."""
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t = snapshot.clock_time
    for mark in sch.lotus_marks():
        if _in_fire_window(t, mark):
            return [
                ReminderHit(
                    key=f"lotus:{mark}",
                    message=sch.LOTUS_MSG,
                    priority=4,
                )
            ]
    return []


def buyback_ready_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    if not snapshot.in_game:
        return []
    if snapshot.buyback_cooldown == 0 and snapshot.gold >= max(snapshot.buyback_cost, 1):
        if prev and prev.buyback_cooldown > 0:
            return [
                ReminderHit(
                    key="buyback_ready",
                    message="买活冷却好了，金币也够，关键团再考虑买活。",
                    priority=8,
                )
            ]
        if not snapshot.hero_alive and snapshot.buyback_cooldown == 0:
            return [
                ReminderHit(
                    key=f"buyback_while_dead:{snapshot.clock_time // 30}",
                    message="你阵亡了且买活可用，评估是否值得买活保高地或抢目标。",
                    priority=9,
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
                            key=f"ult_ready:{name}",
                            message=f"{name} 已就绪。",
                            priority=4,
                        )
                    ]
    return []


DEFAULT_RULES: list[RuleFn] = [
    water_rune_rule,
    power_rune_rule,
    bounty_rune_rule,
    lotus_pool_rule,
    buyback_ready_rule,
    low_health_rule,
]
