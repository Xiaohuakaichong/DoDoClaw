"""Single audio output worker: one thing speaks at a time (prototype of review H1)."""

from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

PRIO_URGENT = 0  # Roshan / aegis: may jump the queue
PRIO_REMINDER = 1
PRIO_ANSWER = 2
STALE_SEC = {PRIO_URGENT: 10.0, PRIO_REMINDER: 10.0, PRIO_ANSWER: 60.0}


class Speaker:
    def __init__(self, speak_fn: Callable[[str], None]) -> None:
        self._speak = speak_fn
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self.speaking = False
        self.current = ""
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._t.start()

    def set_speak_fn(self, fn: Callable[[str], None]) -> None:
        self._speak = fn

    def say(self, text: str, priority: int = PRIO_ANSWER) -> None:
        text = (text or "").strip()
        if text:
            self._q.put((priority, next(self._seq), time.time(), text))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                prio, _seq, ts, text = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if time.time() - ts > STALE_SEC.get(prio, 30):
                logger.info("drop stale speech (%.1fs): %s", time.time() - ts, text[:40])
                continue
            self.speaking, self.current = True, text
            try:
                self._speak(text)
            except Exception:
                logger.exception("speak failed")
            finally:
                self.speaking, self.current = False, ""

    def stop(self) -> None:
        self._stop.set()
