"""DoDoClaw pywebview prototype: main window + in-game overlay.

Run:  python -m dodoclaw webui
Backend (GSI server, reminders, coach, voice) is the existing DoDoClawService;
this module only adds the web UI layer and a JS<->Python bridge.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATIC = Path(__file__).resolve().parent / "static"
OV_W, OV_H, OV_COMPACT = 320, 300, (250, 44)
URGENT_KEYS = ("roshan", "aegis", "肉山", "盾")


def _hero_key(name: str) -> str:
    return (name or "").replace("npc_dota_hero_", "")


_HERO_ZH: dict[str, str] | None = None


def hero_zh(key: str) -> str:
    """Chinese display name from data/hero_aliases.json (falls back to the key)."""
    global _HERO_ZH
    if _HERO_ZH is None:
        import json

        _HERO_ZH = {}
        try:
            path = Path(__file__).resolve().parents[1] / "data" / "hero_aliases.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            for h in data.get("heroes") or []:
                _HERO_ZH[_hero_key(h.get("key", ""))] = h.get("name_zh") or ""
        except Exception:
            logger.exception("hero_aliases.json load failed")
    return _HERO_ZH.get(key) or key


def _release_focus_to_dota() -> bool:
    """Give keyboard focus back to the Dota 2 window (Windows only)."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "Dota 2")
        if not hwnd:
            return False
        # Alt key tap lets SetForegroundWindow succeed from a background process
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        logger.exception("release focus failed")
        return False


class Bridge:
    """Methods here are callable from JS as window.pywebview.api.<name>()."""

    def __init__(self) -> None:
        from dodoclaw.service import DoDoClawService
        from dodoclaw.webui.icons import IconCache
        from dodoclaw.webui.speaker import PRIO_REMINDER, PRIO_URGENT, Speaker
        from dodoclaw.webui.timers import MatchTimers

        self._prio = (PRIO_URGENT, PRIO_REMINDER)
        self._svc = DoDoClawService()
        self._icons = IconCache()
        self._timers = MatchTimers()
        self._speaker = Speaker(lambda text: self._svc.tts.speak(text))
        # Route reminders through the single speaker instead of the service's inline TTS
        self._svc.reminders.on_reminder = self._on_reminder
        self._main_win = None
        self._ov_win = None
        self.compact = False
        self.overlay_forced: bool | None = None
        self.reduce_motion = False
        self._busy = False
        self._answer: dict[str, Any] = {}
        self._alert: dict[str, Any] = {}
        self._error = ""
        self._last_ask_ms: int | None = None

    # ── backend events ───────────────────────────────
    def _on_reminder(self, ev) -> None:
        urgent = any(k in (ev.key or "") or k in ev.message for k in URGENT_KEYS)
        self._alert = {"text": ev.message, "urgent": urgent, "at": time.time()}
        self._speaker.say(ev.message, self._prio[0] if urgent else self._prio[1])

    # ── JS API ───────────────────────────────────────
    def state(self) -> dict[str, Any]:
        svc = self._svc
        snap = svc.snapshot()
        raw = snap.raw or {}
        self._timers.ingest(raw)
        m = raw.get("map") or {}
        age = time.time() - snap.updated_at if snap.updated_at else None
        online = age is not None and age < 35  # GSI heartbeat is 30s
        items = [i.get("name", "") for i in snap.items[:6]]
        alert = self._alert if self._alert and time.time() - self._alert["at"] < 8 else {}
        key_ok = bool((svc.coach.api_key or "").strip())
        return {
            "gsi": {
                "online": online,
                "age": None if age is None else int(age),
                "updates": svc.gsi_update_count,
                "addr": f"{svc.gsi.host}:{svc.gsi.port}",
            },
            "in_game": snap.in_game,
            "game_state": snap.game_state,
            "clock": snap.clock_time,
            "clock_mmss": snap.clock_mmss,
            "daytime": snap.daytime if "daytime" in m else None,
            "paused": bool(m.get("paused")) if "paused" in m else None,
            "hero": _hero_key(snap.hero_name),
            "hero_zh": hero_zh(_hero_key(snap.hero_name)) if snap.hero_name else "",
            "level": snap.hero_level,
            "alive": snap.hero_alive,
            "kda": [snap.kills, snap.deaths, snap.assists],
            "lh": [snap.last_hits, snap.denies],
            "gold": snap.gold,
            "gpm": snap.gpm,
            "items": [x for x in items if x and x != "empty"],
            "timers": self._timers.compute(snap.clock_time) if snap.in_game else [],
            "coach": {"provider": svc.provider_name, "model": svc.coach.model, "key_ok": key_ok},
            "voice": {"tts": svc.tts_backend, "stt": svc.stt_backend},
            "speaking": self._speaker.speaking,
            "busy": self._busy,
            "answer": self._answer,
            "alert": alert,
            "error": self._error,
            "compact": self.compact,
            "reduce_motion": self.reduce_motion,
        }

    def icon(self, kind: str, key: str) -> str:
        return self._icons.data_url(kind, key)

    def ask(self, text: str, voice: bool = True) -> bool:
        text = (text or "").strip()
        if not text or self._busy:
            return False
        self._busy, self._error = True, ""
        t0 = time.time()

        def work() -> None:
            try:
                ans = self._svc.ask(text, speak=False) or "（空回复，请检查模型 / 额度）"
                self._answer = {
                    "q": text,
                    "text": ans,
                    "clock": self._svc.snapshot().clock_mmss,
                    "ms": int((time.time() - t0) * 1000),
                }
                if voice:
                    self._speaker.say(ans)
            except Exception as exc:
                logger.exception("ask failed")
                self._error = str(exc)[:200]
            finally:
                self._busy = False

        threading.Thread(target=work, name="ask", daemon=True).start()
        return True

    def listen(self) -> bool:
        if self._busy:
            return False
        if self._svc.stt_backend == "mock":
            self._error = "语音识别还没配置（当前是 mock），先用打字提问"
            return False
        self._busy = True

        def work() -> None:
            try:
                text = self._svc.listen_once()
            except Exception as exc:
                self._error = f"录音失败: {exc}"[:200]
                text = ""
            self._busy = False
            if text:
                self.ask(text, voice=True)
            elif not self._error:
                self._error = "没听清，再说一次"

        threading.Thread(target=work, name="listen", daemon=True).start()
        return True

    def release_focus(self) -> bool:
        return _release_focus_to_dota()

    def set_reduce_motion(self, on: bool) -> bool:
        self.reduce_motion = bool(on)
        return self.reduce_motion

    def toggle_overlay(self) -> bool:
        shown = not (self.overlay_forced if self.overlay_forced is not None else False)
        self.overlay_forced = shown
        if self._ov_win:
            self._ov_win.show() if shown else self._ov_win.hide()
        return shown

    def toggle_compact(self) -> bool:
        self.compact = not self.compact
        if self._ov_win:
            w, h = OV_COMPACT if self.compact else (OV_W, OV_H)
            self._ov_win.resize(w, h)
        return self.compact

    def minimize(self) -> None:
        if self._main_win:
            self._main_win.minimize()

    def close(self) -> None:
        try:
            self._svc.stop()
            self._speaker.stop()
        finally:
            for w in (self._ov_win, self._main_win):
                try:
                    if w:
                        w.destroy()
                except Exception:
                    pass

    # ── background loop ──────────────────────────────
    def _watch(self) -> None:
        """Auto show/hide overlay with the match; re-assert topmost every 2s."""
        shown = False
        while True:
            time.sleep(2.0)
            try:
                want = self._svc.snapshot().in_game
                if self.overlay_forced is not None:
                    want = self.overlay_forced
                if self._ov_win and want != shown:
                    self._ov_win.show() if want else self._ov_win.hide()
                    shown = want
                if self._ov_win and shown:
                    self._ov_win.on_top = True
            except Exception:
                logger.debug("watch loop", exc_info=True)


def run_webui(debug: bool = False) -> int:
    from dodoclaw.webui.webview2 import require_webview2

    if not require_webview2():
        return 3
    import webview

    bridge = Bridge()
    bridge._svc.start()
    bridge._main_win = webview.create_window(
        "DoDoClaw",
        url=str(STATIC / "main.html"),
        js_api=bridge,
        width=1080,
        height=720,
        min_size=(960, 640),
        frameless=True,
        easy_drag=False,
        background_color="#06080c",
    )
    bridge._ov_win = webview.create_window(
        "DoDoClaw 小窗",
        url=str(STATIC / "overlay.html"),
        js_api=bridge,
        width=OV_W,
        height=OV_H,
        x=24,
        y=120,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        resizable=False,
        hidden=True,
        focus=True,
        background_color="#000000",
    )
    bridge._main_win.events.closed += bridge.close

    def _started() -> None:
        threading.Thread(target=bridge._watch, name="overlay-watch", daemon=True).start()

    webview.start(_started, gui="edgechromium" if os.name == "nt" else None,
                  http_server=True, debug=debug)
    return 0
