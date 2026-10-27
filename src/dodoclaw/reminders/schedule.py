"""Reminder timings (patch 7.41f). Source: domain/reminder-budget.md — do not invent."""

from __future__ import annotations

from dataclasses import dataclass

from dodoclaw.gsi.objectives import (
    AEGIS_SEC,
    ROSHAN_MIN,
    SHRINE_INTERVAL,
    SHRINE_START,
    TORMENTOR_FIRST,
)

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

# ---- 智慧神龛 (shrine) — all positions; 7:00 then every 7 min ----
SHRINE_WARN_SEC = 15
SHRINE_UNTIL_SEC = 60 * 60
SHRINE_MSG = "15 秒后智慧神龛"

# ---- 痛苦魔方 (Tormentor) — all positions ----
# Only the 15:00 first spawn: GSI has no Tormentor-kill event to time respawns.
TORMENTOR_WARN_SEC = 30
TORMENTOR_MSG = "魔方 30 秒后刷新"  # settings-page copy

# ---- 肉山 (Roshan) — from the roshan_killed GSI event; window 8–11 min ----
# GSI can't see whether he is up: say "can respawn", never "is up".
ROSHAN_WARN_SEC = 30
ROSHAN_MSG = "肉山快复活了"  # settings-page copy; 30 s before the earliest respawn

# ---- 不朽盾 (Aegis) — 5 min after aegis_picked_up; warn with 1 min left ----
AEGIS_WARN_SEC = 60
AEGIS_MSG = "盾还剩 1 分钟"  # settings-page copy

# ---- 没带回城卷轴 (TP) — checked once at 10:00 and once at 20:00 ----
TP_CHECK_SEC: tuple[int, ...] = (10 * 60, 20 * 60)
TP_CHECK_WINDOW_SEC = 30  # dead / no item data at the mark → check later in this window
TP_MSG = "身上没带回城卷轴，记得补一个"

# ---- 买活 (buyback) — "25 分钟后变为可用 / 买大件后钱不够买活" ----
BUYBACK_LATE_SEC = 25 * 60
BUYBACK_READY_MSG = "买活可用了，关键团再考虑买活。"
BUYBACK_DEAD_MSG = "你阵亡了且买活可用，评估是否值得买活保高地或抢目标。"
BUYBACK_SHORT_MSG = "现在的钱不够买活了，后期注意留买活钱"

# How far (game seconds) a packet may jump past a fire point and still fire.
CATCHUP_SEC = 5


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


def shrine_windows(until: int = SHRINE_UNTIL_SEC) -> list[WarnWindow]:
    return [
        WarnWindow("shrine", t, SHRINE_WARN_SEC, SHRINE_MSG)
        for t in range(SHRINE_START, until + 1, SHRINE_INTERVAL)
    ]


def tormentor_windows() -> list[WarnWindow]:
    return [WarnWindow("cube", TORMENTOR_FIRST, TORMENTOR_WARN_SEC, TORMENTOR_MSG)]


def roshan_warn_at(killed_at: int) -> int:
    return killed_at + ROSHAN_MIN - ROSHAN_WARN_SEC


def aegis_warn_at(picked_at: int) -> int:
    return picked_at + AEGIS_SEC - AEGIS_WARN_SEC
