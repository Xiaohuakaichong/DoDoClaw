from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from dodoclaw.gsi.objectives import MatchEvents
from dodoclaw.gsi.state import GameSnapshot, GameStateStore
from dodoclaw.reminders.rules import ReminderHit, RuleFn, default_rules, ult_ready_rule

logger = logging.getLogger(__name__)


@dataclass
class ReminderEvent:
    key: str
    message: str
    priority: int
    created_at: float


class ReminderEngine:
    """Evaluate reminder rules against latest GSI snapshot.

    Every hit key names one occurrence (``water_rune:120``, ``roshan:1200``), so a
    key fires at most once per match — a game paused inside a fire window no
    longer repeats it every ``cooldown_sec``. ``cooldown_sec`` (wall clock) still
    spaces out messages of the same family.
    """

    def __init__(
        self,
        store: GameStateStore,
        rules: list[RuleFn] | None = None,
        cooldown_sec: float = 25.0,
        announce_ult_ready: bool = False,
        on_reminder: Callable[[ReminderEvent], None] | None = None,
        events: MatchEvents | None = None,
    ) -> None:
        self.store = store
        # events: shared Roshan / Aegis tracker (fed by the service on every packet)
        self.rules = list(rules) if rules is not None else default_rules(events)
        if announce_ult_ready and ult_ready_rule not in self.rules:
            self.rules.append(ult_ready_rule)
        self.cooldown_sec = cooldown_sec
        self.on_reminder = on_reminder
        self._prev: GameSnapshot | None = None
        self._last_fired: dict[str, float] = {}
        self._match_keys: set[str] = set()
        self._match: tuple[str, int] = ("", 0)

    def _track_match(self, snap: GameSnapshot) -> None:
        mid, clock = snap.match_id, snap.clock_time
        last_mid, last_clock = self._match
        # new match id, or the clock jumped far back (new game without a match id)
        if mid != last_mid or clock < last_clock - 60:
            self._match_keys.clear()
        self._match = (mid, clock)

    def tick(self) -> list[ReminderEvent]:
        snap = self.store.get()
        if snap is self._prev:
            return []  # no new GSI packet since the last tick
        self._track_match(snap)
        hits: list[ReminderHit] = []
        for rule in self.rules:
            try:
                hits.extend(rule(snap, self._prev))
            except Exception:
                logger.exception("reminder rule failed: %s", getattr(rule, "__name__", rule))

        now = time.time()
        events: list[ReminderEvent] = []
        for hit in sorted(hits, key=lambda h: -h.priority):
            if hit.key in self._match_keys:
                continue
            last = self._last_fired.get(hit.key, 0.0)
            if now - last < self.cooldown_sec:
                continue
            # also cooldown by message family prefix before ':'
            family = hit.key.split(":", 1)[0]
            fam_last = self._last_fired.get(f"family:{family}", 0.0)
            if now - fam_last < self.cooldown_sec:
                continue

            ev = ReminderEvent(
                key=hit.key,
                message=hit.message,
                priority=hit.priority,
                created_at=now,
            )
            events.append(ev)
            self._match_keys.add(hit.key)
            self._last_fired[hit.key] = now
            self._last_fired[f"family:{family}"] = now
            if self.on_reminder:
                try:
                    self.on_reminder(ev)
                except Exception:
                    logger.exception("on_reminder failed")

        self._prev = snap
        return events
