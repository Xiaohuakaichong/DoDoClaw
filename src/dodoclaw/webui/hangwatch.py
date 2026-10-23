"""Hang watchdog: if the window (UI) thread stops answering, write every
thread's stack to logs/hang.log next to the exe.

Uses faulthandler.dump_traceback_later, whose timer runs in C and does not need
the GIL, so the dump still happens when a thread holding the GIL is stuck (the
overlay freeze was exactly that). The Python loop only re-arms the timer after
each successful ping of the UI thread; the ping itself (SendMessageTimeout)
releases the GIL. Costs one message every few seconds.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

PING_EVERY = 3.0  # s between pings
PING_TIMEOUT_MS = 5000  # one ping may take this long before it counts as a miss
DUMP_AFTER = 15.0  # s with no successful ping -> dump all stacks


def ping_hwnd(hwnd: int, timeout_ms: int = PING_TIMEOUT_MS, user32=None) -> bool:
    """True if the thread owning hwnd processed a WM_NULL within timeout_ms."""
    import ctypes
    from ctypes import wintypes

    if user32 is None:
        if sys.platform != "win32":
            return True
        user32 = ctypes.windll.user32
    WM_NULL, SMTO_ABORTIFHUNG = 0x0000, 0x0002
    res = ctypes.c_size_t(0)
    ok = user32.SendMessageTimeoutW(
        wintypes.HWND(hwnd), WM_NULL, 0, 0, SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(res)
    )
    return bool(ok)


class HangWatch:
    def __init__(
        self,
        log_path: Path,
        get_hwnd: Callable[[], int | None],
        ping: Callable[[int], bool] = ping_hwnd,
        arm: Callable[..., None] = faulthandler.dump_traceback_later,
        disarm: Callable[[], None] = faulthandler.cancel_dump_traceback_later,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.log_path = Path(log_path)
        self._get_hwnd, self._ping, self._arm, self._disarm, self._sleep = get_hwnd, ping, arm, disarm, sleep
        self._file = None
        self._stop = threading.Event()
        self.misses = 0
        self.episodes = 0
        self._hwnd: int | None = None

    def _open(self):
        if self._file is None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            # Must already be open when the C timer fires (nothing can be opened then).
            self._file = open(self.log_path, "a", encoding="utf-8")  # noqa: SIM115
        return self._file

    def step(self) -> bool:
        """One ping. Returns True when the UI thread answered."""
        if not self._hwnd:  # read once: no .NET property access while the app may be stuck
            self._hwnd = self._get_hwnd()
        hwnd = self._hwnd
        if not hwnd:
            return True
        f = self._open()
        self._arm(DUMP_AFTER, repeat=False, file=f, exit=False)
        if self._ping(hwnd):
            self._disarm()
            if self.misses:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 窗口线程恢复响应（卡了约 {self.misses} 次检查）\n")
                f.flush()
            self.misses = 0
            return True
        self.misses += 1
        if self.misses == 1:
            self.episodes += 1
            f.write(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} 窗口线程没有响应，"
                    f"{int(DUMP_AFTER)} 秒内还不恢复就记录所有线程的调用栈\n")
            f.flush()
            logger.warning("UI thread not responding; stacks go to %s", self.log_path)
        # Leave the timer armed: it fires once even if this thread can't get the GIL again.
        # Wait past it so one hang gives one dump, not one per ping.
        self._sleep(DUMP_AFTER + 1)
        return False

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:
                logger.debug("hang watch", exc_info=True)
            self._sleep(PING_EVERY)

    def stop(self) -> None:
        self._stop.set()
        try:
            self._disarm()
        except Exception:
            pass

    def start(self) -> threading.Thread:
        t = threading.Thread(target=self.run, name="hang-watch", daemon=True)
        t.start()
        return t