"""Map objectives tracked across GSI packets: Roshan, Aegis, shrines, Tormentor.

Timings follow review-domain.md 1.1 (7.41f). Copy deliberately has no map side
for Roshan / Tormentor until real GSI samples confirm the 7.41 swap.

One ``MatchEvents`` instance is fed every packet (``ingest``); the coach reads
``context_lines`` and the reminder rules / overlay timers read the fields.
"""

from __future__ import annotations

import threading
from typing import Any

SHRINE_START = 420  # 智慧神龛 7:00, then every 7 min
SHRINE_INTERVAL = 420
TORMENTOR_FIRST = 900  # 痛苦魔方 first spawn 15:00
ROSHAN_MIN = 480  # respawn window 8–11 min after the kill
ROSHAN_MAX = 660
AEGIS_SEC = 300  # Aegis expires 5 min after pickup


def _num(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _ev_time(ev: dict[str, Any], offset: int | None, clock: int | None) -> int | None:
    """Event time on the map.clock_time axis.

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


def next_shrine(clock: int) -> int:
    """Clock second of the next 智慧神龛 spawn at or after ``clock``."""
    if clock <= SHRINE_START:
        return SHRINE_START
    k = -(-(clock - SHRINE_START) // SHRINE_INTERVAL)  # ceil
    return SHRINE_START + k * SHRINE_INTERVAL


def mmss(sec: int) -> str:
    sign = "-" if sec < 0 else ""
    sec = abs(int(sec))
    return f"{sign}{sec // 60:02d}:{sec % 60:02d}"


class MatchEvents:
    """Roshan kills / Aegis pickups from GSI ``events``, reset on a new match id."""

    def __init__(self) -> None:
        self.match_id = ""
        self.roshan_killed_at: int | None = None
        self.roshan_kills = 0
        self.aegis_at: int | None = None
        self._seen: set[tuple] = set()
        self._lock = threading.Lock()

    def _reset(self, match_id: str) -> None:
        self.match_id = match_id
        self.roshan_killed_at = None
        self.roshan_kills = 0
        self.aegis_at = None
        self._seen = set()

    def ingest(self, raw: dict[str, Any]) -> None:
        if not isinstance(raw, dict):
            return
        m = raw.get("map") or {}
        mid = str(m.get("matchid") or "")
        clock = _num(m.get("clock_time"))
        gtime = _num(m.get("game_time"))
        offset = gtime - clock if gtime is not None and clock is not None else None
        events = raw.get("events") or []
        if isinstance(events, dict):
            events = list(events.values())
        with self._lock:
            if mid and mid != self.match_id:
                self._reset(mid)
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
                    self.roshan_kills += 1
                elif et == "aegis_picked_up":
                    self.aegis_at = t
                elif et == "aegis_denied":
                    self.aegis_at = None

    def aegis_remaining(self, clock: int) -> int | None:
        if self.aegis_at is None:
            return None
        r = AEGIS_SEC - (clock - self.aegis_at)
        return r if 0 < r <= AEGIS_SEC else None

    def context_lines(self, clock: int) -> list[str]:
        """Objective timers in Chinese for the coach prompt (no map sides)."""
        if clock < 0:
            return []
        out = [f"下个智慧神龛: {mmss(next_shrine(clock))}"]
        if clock < TORMENTOR_FIRST:
            out.append(f"痛苦魔方首次刷新: {mmss(TORMENTOR_FIRST)}")
        if self.roshan_killed_at is None:
            out.append("肉山: 本局还没被击杀（或 GSI 没收到击杀事件）")
        else:
            k = self.roshan_killed_at
            since = clock - k
            if since < ROSHAN_MIN:
                state = "未复活"
            elif since < ROSHAN_MAX:
                state = "可能已复活"
            else:
                state = "已复活"
            out.append(
                f"肉山: 第 {self.roshan_kills} 次击杀于 {mmss(k)}，复活窗口 "
                f"{mmss(k + ROSHAN_MIN)}–{mmss(k + ROSHAN_MAX)}（{state}）"
            )
        r = self.aegis_remaining(clock)
        if r is not None:
            out.append(f"不朽盾: 场上有人持有，约 {r}s 后消失")
        return out
