from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dodoclaw.gsi.state import GameSnapshot


@dataclass(frozen=True)
class ReminderHit:
    key: str
    message: str
    priority: int = 0


RuleFn = Callable[[GameSnapshot, GameSnapshot | None], list[ReminderHit]]


def power_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Power runes spawn at 6:00 then every 2 minutes in modern patches (approx)."""
    if not snapshot.in_game or snapshot.clock_time < 6 * 60:
        return []
    t = snapshot.clock_time
    # Fire in a small window after spawn second
    if t >= 360 and (t - 360) % 120 <= 1:
        mmss = snapshot.clock_mmss
        return [
            ReminderHit(
                key=f"power_rune:{t // 120}",
                message=f"神符点。比赛时间 {mmss}，留意河道神符。",
                priority=5,
            )
        ]
    return []


def bounty_rune_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    """Bounty runes roughly every 3 minutes from 0:00."""
    if not snapshot.in_game or snapshot.clock_time < 0:
        return []
    t = snapshot.clock_time
    if t > 0 and t % 180 <= 1:
        return [
            ReminderHit(
                key=f"bounty_rune:{t // 180}",
                message=f"赏金神符刷新，时间 {snapshot.clock_mmss}。",
                priority=3,
            )
        ]
    return []


def buyback_ready_rule(snapshot: GameSnapshot, prev: GameSnapshot | None) -> list[ReminderHit]:
    if not snapshot.in_game:
        return []
    if snapshot.buyback_cooldown == 0 and snapshot.gold >= max(snapshot.buyback_cost, 1):
        # Only announce transition to ready if we saw cooldown before, or once when dead
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
    power_rune_rule,
    bounty_rune_rule,
    buyback_ready_rule,
    low_health_rule,
    # ult_ready_rule 默认关闭（可在 engine 配置里启用）
]
