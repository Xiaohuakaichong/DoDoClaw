"""Live objective timers for the overlay (pure logic, unit-testable).

Values follow review-domain.md 1.1 (7.41f). Copy deliberately has no map side
for Roshan / Tormentor until real GSI samples confirm the 7.41 swap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dodoclaw.gsi.objectives import (  # noqa: F401  (re-exported for callers/tests)
    AEGIS_SEC,
    ROSHAN_MAX,
    ROSHAN_MIN,
    SHRINE_INTERVAL,
    SHRINE_START,
    TORMENTOR_FIRST,
    MatchEvents,
    next_shrine,
)


@dataclass
class Timer:
    key: str
    name: str
    icon: str  # "shrine" | "cube" | "spark" | "item:aegis"
    remain: int
    total: int
    color: str  # css var name
    hot: bool = False
    note: str = ""


class MatchTimers(MatchEvents):
    """Overlay rows built on the shared Roshan / Aegis event tracker."""

    def compute(self, clock: int) -> list[dict[str, Any]]:
        out: list[Timer] = []
        if clock >= 0:
            nxt = next_shrine(clock)
            if nxt == clock:  # spawning right now: count down to the one after
                nxt += SHRINE_INTERVAL
            r = nxt - clock
            out.append(Timer("shrine", "智慧神龛", "shrine", r, SHRINE_INTERVAL, "--info",
                             hot=False))
            if clock < TORMENTOR_FIRST:
                out.append(Timer("cube", "痛苦魔方", "cube", TORMENTOR_FIRST - clock,
                                 TORMENTOR_FIRST, "--gold"))
        if self.roshan_killed_at is not None:
            since = clock - self.roshan_killed_at
            if since < ROSHAN_MIN:
                r = ROSHAN_MIN - since
                out.append(Timer("roshan", "肉山最早复活", "spark", r, ROSHAN_MIN, "--brand-2",
                                 hot=r <= 30, note=f"最晚还有 {ROSHAN_MAX - since}s"))
            elif since < ROSHAN_MAX:
                r = ROSHAN_MAX - since
                out.append(Timer("roshan", "肉山可能已复活", "spark", r,
                                 ROSHAN_MAX - ROSHAN_MIN, "--brand-2", note="最晚复活倒计时"))
        if self.aegis_at is not None:
            r = AEGIS_SEC - (clock - self.aegis_at)
            if 0 < r <= AEGIS_SEC:
                out.append(Timer("aegis", "不朽盾", "item:aegis", r, AEGIS_SEC, "--warn",
                                 hot=r <= 60))
        out.sort(key=lambda t: (not t.hot, t.remain))
        return [asdict(t) for t in out]
