"""Live objective timers for the overlay (pure logic, unit-testable).

Values follow review-domain.md 1.1 (7.41f). Copy deliberately has no map side
for Roshan / Tormentor until real GSI samples confirm the 7.41 swap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SHRINE_START = 420
SHRINE_INTERVAL = 420
TORMENTOR_FIRST = 900
ROSHAN_MIN = 480
ROSHAN_MAX = 660
AEGIS_SEC = 300


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


def _num(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _ev_time(ev: dict[str, Any], offset: int | None, clock: int | None) -> int | None:
    """Event time on the map.clock_time axis (what compute() compares against).

    GSI events carry ``game_time`` (counts from load-in); clock_time starts at the
    horn, so convert with offset = map.game_time - map.clock_time. Without an
    offset, fall back to the current map.clock_time when the event arrives.
    """
    if "clock_time" in ev:
        return _num(ev["clock_time"])
    gt = _num(ev.get("game_time", ev.get("time")))
    if gt is not None and offset is not None:
        return gt - offset
    return clock


class MatchTimers:
    def __init__(self) -> None:
        self.match_id = ""
        self.roshan_killed_at: int | None = None
        self.aegis_at: int | None = None
        self._seen: set[tuple] = set()

    def _reset(self, match_id: str) -> None:
        self.__init__()
        self.match_id = match_id

    def ingest(self, raw: dict[str, Any]) -> None:
        m = raw.get("map") or {}
        mid = str(m.get("matchid") or "")
        if mid and mid != self.match_id:
            self._reset(mid)
        clock = _num(m.get("clock_time"))
        gtime = _num(m.get("game_time"))
        offset = gtime - clock if gtime is not None and clock is not None else None
        events = raw.get("events") or []
        if isinstance(events, dict):
            events = list(events.values())
        for ev in events:
            if not isinstance(ev, dict):
                continue
            et = str(ev.get("event_type") or "")
            t = _ev_time(ev, offset, clock)
            sig = (et, ev.get("game_time", t))
            if t is None or sig in self._seen:
                continue
            self._seen.add(sig)
            if et == "roshan_killed":
                self.roshan_killed_at = t
            elif et == "aegis_picked_up":
                self.aegis_at = t

    def compute(self, clock: int) -> list[dict[str, Any]]:
        out: list[Timer] = []
        if clock >= 0:
            nxt = SHRINE_START if clock < SHRINE_START else (
                (clock - SHRINE_START) // SHRINE_INTERVAL + 1
            ) * SHRINE_INTERVAL + SHRINE_START
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
