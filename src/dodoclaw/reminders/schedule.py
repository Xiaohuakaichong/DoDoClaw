"""Reminder timings (patch 7.41f). Source: domain/reminder-budget.md — do not invent."""

from __future__ import annotations

from dataclasses import dataclass

# ---- 河道水符 (water) — default pos 2 ----
WATER_SPAWN_SEC: tuple[int, ...] = (2 * 60, 4 * 60)  # 2:00, 4:00 only
WATER_WARN_SEC = 15
WATER_MSG = "15 秒后河道水符"

# ---- 河道神符 / 能量神符 (power) — default pos 2 ----
POWER_FIRST_SEC = 6 * 60  # 6:00
POWER_INTERVAL_SEC = 2 * 60
POWER_UNTIL_SEC = 20 * 60  # budget table: 报到 20:00
POWER_WARN_SEC = 15
POWER_MSG = "15 秒后河道神符"

# ---- 赏金神符 / 金币神符 (bounty) — default pos 4/5 ----
BOUNTY_INTERVAL_SEC = 3 * 60
BOUNTY_SKIP_SEC = 0  # skip the 0:00 spawn
BOUNTY_UNTIL_SEC = 15 * 60  # budget table: 报到 15:00
BOUNTY_WARN_SEC = 20  # from the 3:00 spawn onward
BOUNTY_MSG = "20 秒后赏金神符"

# ---- 莲花池 (lotus) — default pos 3/4/5 ----
# Global clock every 3 min (pickup does NOT reset). Remind at the mark from 6:00
# every 6 minutes. Wording must NOT state counts.
LOTUS_FIRST_SEC = 6 * 60
LOTUS_INTERVAL_SEC = 6 * 60
LOTUS_WARN_SEC = 0  # at the mark, no early warn
LOTUS_MSG = "莲花池该刷新了，路过可以采"


@dataclass(frozen=True)
class WarnWindow:
    """A one-second fire window at (spawn - warn)."""

    family: str
    spawn_sec: int
    warn_sec: int
    message: str

    @property
    def fire_at(self) -> int:
        return self.spawn_sec - self.warn_sec


def water_windows() -> list[WarnWindow]:
    return [
        WarnWindow("water_rune", s, WATER_WARN_SEC, WATER_MSG) for s in WATER_SPAWN_SEC
    ]


def power_windows(until: int = POWER_UNTIL_SEC) -> list[WarnWindow]:
    out: list[WarnWindow] = []
    t = POWER_FIRST_SEC
    while t <= until:
        out.append(WarnWindow("power_rune", t, POWER_WARN_SEC, POWER_MSG))
        t += POWER_INTERVAL_SEC
    return out


def bounty_windows(until: int = BOUNTY_UNTIL_SEC) -> list[WarnWindow]:
    out: list[WarnWindow] = []
    t = BOUNTY_INTERVAL_SEC  # start at 3:00 (skip 0:00)
    while t <= until:
        out.append(WarnWindow("bounty_rune", t, BOUNTY_WARN_SEC, BOUNTY_MSG))
        t += BOUNTY_INTERVAL_SEC
    return out


def lotus_marks(until: int = 40 * 60) -> list[int]:
    out: list[int] = []
    t = LOTUS_FIRST_SEC
    while t <= until:
        out.append(t)
        t += LOTUS_INTERVAL_SEC
    return out
