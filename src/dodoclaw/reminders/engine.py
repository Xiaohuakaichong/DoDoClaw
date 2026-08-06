from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from dodoclaw.gsi.state import GameSnapshot, GameStateStore
from dodoclaw.reminders.rules import DEFAULT_RULES, ReminderHit, RuleFn, ult_ready_rule

logger = logging.getLogger(__name__)


@dataclass
class ReminderEvent:
    key: str
    message: str
    priority: int
    created_at: float


class ReminderEngine:
    """Evaluate reminder rules against latest GSI snapshot."""

    def __init__(
        self,
        store: GameStateStore,
        rules: list[RuleFn] | None = None,
        cooldown_sec: float = 25.0,
        announce_ult_ready: bool = False,
        on_reminder: Callable[[ReminderEvent], None] | None = None,
    ) -> None:
        self.store = store
        self.rules = list(rules or DEFAULT_RULES)
        if announce_ult_ready and ult_ready_rule not in self.rules:
            self.rules.append(ult_ready_rule)
        self.cooldown_sec = cooldown_sec
        self.on_reminder = on_reminder
        self._prev: GameSnapshot | None = None
        self._last_fired: dict[str, float] = {}

    def tick(self) -> list[ReminderEvent]:
        snap = self.store.get()
        hits: list[ReminderHit] = []
        for rule in self.rules:
            try:
                hits.extend(rule(snap, self._prev))
            except Exception:
                logger.exception("reminder rule failed: %s", getattr(rule, "__name__", rule))

        now = time.time()
        events: list[ReminderEvent] = []
        for hit in sorted(hits, key=lambda h: -h.priority):
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
            self._last_fired[hit.key] = now
            self._last_fired[f"family:{family}"] = now
            if self.on_reminder:
                try:
                    self.on_reminder(ev)
                except Exception:
                    logger.exception("on_reminder failed")

        self._prev = snap
        return events
