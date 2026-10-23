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
OV_W, OV_H, OV_COMPACT = 320, 300, (250, 40)  # window == card (no shadow margin); JS fit() refines
OV_BG = "#0a0c11"  # opaque card colour: no white flash, no grey corners
URGENT_KEYS = ("roshan", "aegis", "肉山", "盾")
OV_POS = (24, 120)

TTS_ZH = {"mock": "未配置", "edge": "Edge 免费声音", "stepfun_plan": "阶跃语音", "stepfun": "阶跃语音"}
STT_ZH = {"mock": "关", "whisper": "本地识别", "stepfun_plan": "云端识别", "stepfun": "云端识别"}
GAME_STATE_ZH = {
    "DOTA_GAMERULES_STATE_INIT": "准备中",
    "DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD": "加载中",
    "DOTA_GAMERULES_STATE_HERO_SELECTION": "选人中",
    "DOTA_GAMERULES_STATE_STRATEGY_TIME": "策略时间",
    "DOTA_GAMERULES_STATE_TEAM_SHOWCASE": "展示阵容",
    "DOTA_GAMERULES_STATE_PRE_GAME": "出兵前",
    "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS": "对局中",
    "DOTA_GAMERULES_STATE_POST_GAME": "对局结束",
}


def _open_path(path: Path) -> bool:
    """Open a folder in Explorer (Windows) / the desktop file manager (dev)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        logger.exception("open folder failed")
        return False


def _hero_key(name: str) -> str:
    return (name or "").replace("npc_dota_hero_", "")


_ITEM_ZH: dict[str, str] | None = None


def item_zh(key: str) -> str:
    """Chinese item name from data/item_names_zh.json (Valve datafeed, schinese)."""
    global _ITEM_ZH
    if _ITEM_ZH is None:
        import json

        try:
            path = Path(__file__).resolve().parents[1] / "data" / "item_names_zh.json"
            _ITEM_ZH = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _ITEM_ZH = {}
    k = (key or "").removeprefix("item_")
    return _ITEM_ZH.get(k, "物品")


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


def _preview_voice_zh(configured: str) -> str:
    from dodoclaw.webui import tts_preview

    return tts_preview.voice_label(tts_preview.edge_voice(configured))


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("dodoclaw")
    except Exception:
        return "0.5.0"


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
        self._ov_shape = ""
        self.reduce_motion = False
        self._busy = False
        self._answer: dict[str, Any] = {}
        self._alert: dict[str, Any] = {}
        self._error = ""
        self._coach_err: dict[str, Any] = {}  # {kind, reason_zh} of the last failed coach call
        self._last_ask_ms: int | None = None
        # settings page
        from dodoclaw.paths import app_dir
        from dodoclaw.webui import keycheck, settings_store

        self._env_path = app_dir() / ".env"
        self._env_names = keycheck.env_names_in_file(self._env_path)
        self._ui_path = self._svc.settings.yaml_path()
        self.ui = settings_store.load(self._ui_path)
        self.reduce_motion = bool(self.ui["reduce_motion"])
        if self.ui["voice_ask"] is None:  # first run: keep whatever backend is configured
            self.ui["voice_ask"] = self._svc.stt_backend != "mock"
        elif self.ui["voice_ask"] and self._svc.stt_backend == "mock":
            self._apply_stt(True)
        self._last_test: dict[str, Any] = {}

    # ── backend events ───────────────────────────────
    def _on_reminder(self, ev) -> None:
        from dodoclaw.webui.settings_store import FAMILY_TO_ROW

        row = FAMILY_TO_ROW.get((ev.key or "").split(":", 1)[0])
        if row and not self.ui["reminders"].get(row, {}).get("on", True):
            return  # switched off on the settings page
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
        cerr = self._coach_err
        coach_error = {"kind": cerr["kind"], "reason_zh": cerr["reason_zh"]} if cerr and key_ok else None
        return {
            "gsi": {
                "online": online,
                "age": None if age is None else int(age),
                "updates": svc.gsi_update_count,
                "addr": f"{svc.gsi.host}:{svc.gsi.port}",
            },
            "in_game": snap.in_game,
            "game_state": snap.game_state,
            "game_state_zh": GAME_STATE_ZH.get(snap.game_state or "", "在客户端"),
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
            "items_zh": [item_zh(x) for x in items if x and x != "empty"],
            "timers": self._timers.compute(snap.clock_time) if snap.in_game else [],
            "coach": {"provider": svc.provider_name, "model": svc.coach.model, "key_ok": key_ok, "error": coach_error},
            "voice": {
                "tts": svc.tts_backend,
                "stt": svc.stt_backend,
                "tts_zh": TTS_ZH.get(svc.tts_backend, "已配置"),
                "stt_zh": STT_ZH.get(svc.stt_backend, "已配置"),
            },
            "speaking": self._speaker.speaking,
            "busy": self._busy,
            "answer": self._answer,
            "alert": alert,
            "error": self._error,
            "compact": self.compact,
            "reduce_motion": self.reduce_motion,
            "ov_opacity": self.ui["overlay_opacity"],
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
                ans = self._svc.ask(text, speak=False, raise_errors=True) or "（空回复，请检查模型 / 额度）"
                self._answer = {
                    "q": text,
                    "text": ans,
                    "clock": self._svc.snapshot().clock_mmss,
                    "ms": int((time.time() - t0) * 1000),
                }
                if (self._svc.coach.api_key or "").strip():
                    self._coach_err = {}  # a real answer came back: the card goes back to normal
                if voice:
                    self._speaker.say(ans)
            except Exception as exc:
                self._set_coach_error(exc)
            finally:
                self._busy = False

        threading.Thread(target=work, name="ask", daemon=True).start()
        return True

    def _set_coach_error(self, exc: BaseException) -> None:
        """Remember a failed coach call as a Chinese reason (never the exception text)."""
        from dodoclaw.coach.errors import classify

        err = classify(exc)
        logger.warning("coach call failed: %s (%s)", err["kind"], type(exc).__name__)
        self._coach_err = {"kind": err["kind"], "reason_zh": err["reason_zh"], "at": time.time()}
        self._error = err["reason_zh"]

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
        self.ui["reduce_motion"] = self.reduce_motion
        self._save_ui()
        return self.reduce_motion

    # ── settings page ────────────────────────────────
    def _save_ui(self) -> None:
        from dodoclaw.webui import settings_store

        try:
            settings_store.save(self._ui_path, self.ui)
        except Exception:
            logger.exception("save settings failed")

    def _key_status(self) -> dict[str, Any]:
        from dodoclaw.webui.keycheck import key_status

        c = self._svc.coach
        return key_status(self._svc.provider_id, self._svc.provider_name, c.api_key or "")

    def _stt_default(self, key: dict[str, Any]) -> str:
        return "cloud" if key["has_stt"] else "local"

    def _apply_stt(self, on: bool) -> str:
        """Switch the speech-recognition backend. Returns an error in Chinese or ''."""
        import importlib.util

        if not on:
            if self._svc.stt_backend != "mock":
                self._svc.reload_voice(stt_backend="mock")
            return ""
        key = self._key_status()
        mode = self.ui.get("stt_mode") or self._stt_default(key)
        if mode == "local":
            if importlib.util.find_spec("faster_whisper") is None:
                return "这个版本还没带本地识别组件，先选云端识别或打字提问"
            backend = "whisper"
        else:
            if not key["stepfun_key"]:
                return "云端识别要阶跃的 Key：在 .env 里加 STEPFUN_API_KEY=你的Key，再点“重新读取”"
            backend = key["provider"] if key["has_stt"] else "stepfun_plan"
        try:
            self._svc.reload_voice(stt_backend=backend)
        except Exception:
            logger.exception("enable stt failed")
            return "语音识别没能启动，详情见日志"
        if self._svc.stt_backend == "mock":
            return "语音识别没能启动，详情见日志"
        return ""

    def settings_state(self) -> dict[str, Any]:
        from dodoclaw.webui import settings_store

        svc = self._svc
        key = self._key_status()
        snap = svc.snapshot()
        age = time.time() - snap.updated_at if snap.updated_at else None
        icons = list(self._icons.root.rglob("*.png")) if self._icons.root.exists() else []
        try:
            from dodoclaw.gsi_install import resolve_dota_cfg_target

            target = resolve_dota_cfg_target()
        except Exception:
            target = None
        cfg = (target / "gamestate_integration_dodoclaw.cfg") if target else None
        import importlib.util

        return {
            "ui": self.ui,
            "budget": settings_store.budget(self.ui["reminders"]),
            "budget_cap": settings_store.BUDGET_CAP,
            "over_cap_hint": settings_store.OVER_CAP_HINT,
            "pending": sorted(settings_store.PENDING),
            "key": key,
            "last_test": self._last_test,
            "voice": {
                "ask_on": bool(self.ui["voice_ask"]) and svc.stt_backend != "mock",
                "stt_mode": self.ui.get("stt_mode") or self._stt_default(key),
                "stt_default": self._stt_default(key),
                "stt_zh": STT_ZH.get(svc.stt_backend, "已配置"),
                "whisper_ready": importlib.util.find_spec("faster_whisper") is not None,
                "tts_on": svc.tts_backend != "mock",
                "tts_zh": TTS_ZH.get(svc.tts_backend, "已配置"),
                "preview_voice_zh": _preview_voice_zh(getattr(svc, "tts_voice", "")),
            },
            "adv": {
                "online": age is not None and age < 35,
                "updates": svc.gsi_update_count,
                "age": None if age is None else round(age, 1),
                "host": svc.gsi.host,
                "port": svc.gsi.port,
                "token_set": bool(svc.gsi.auth_token),
                "cfg_path": str(cfg) if cfg else "",
                "cfg_ok": bool(cfg and cfg.exists()),
                "recording": svc._recorder is not None,
                "icon_count": len(icons),
                "icon_mb": round(sum(p.stat().st_size for p in icons) / 1048576, 1),
                "icon_dir": str(self._icons.root),
            },
            "version": _version(),
        }

    def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply one change from the settings page. Returns {ok, msg}."""
        from dodoclaw.webui import settings_store

        patch = patch or {}
        msg = ""
        if "positions" in patch:
            self.ui = settings_store.apply_positions(self.ui, list(patch["positions"] or []))
        if "reminder" in patch:
            row = str(patch["reminder"])
            if "on" in patch:
                self.ui, msg = settings_store.toggle_reminder(self.ui, row, bool(patch["on"]))
            # "lead" is ignored: lead times are not editable until the engine supports them
        if "overlay_opacity" in patch:
            self.ui["overlay_opacity"] = max(40, min(100, int(patch["overlay_opacity"])))
        if "auto_overlay" in patch:
            self.ui["auto_overlay"] = bool(patch["auto_overlay"])
        if "stt_mode" in patch and patch["stt_mode"] in ("local", "cloud"):
            self.ui["stt_mode"] = patch["stt_mode"]
            if self.ui["voice_ask"]:
                msg = self._apply_stt(True)
                if msg:
                    self.ui["voice_ask"] = False
                    self._apply_stt(False)
        if "voice_ask" in patch:
            on = bool(patch["voice_ask"])
            msg = self._apply_stt(on)
            self.ui["voice_ask"] = on and not msg
        if msg and "reminder" in patch:
            return {"ok": False, "msg": msg}
        self._save_ui()
        return {"ok": not msg, "msg": msg}

    def open_app_dir(self) -> bool:
        """Folder holding .env: next to the exe, or the project root from source."""
        from dodoclaw.paths import app_dir

        return _open_path(app_dir())

    def open_log_dir(self) -> bool:
        from dodoclaw.paths import app_dir

        return _open_path(app_dir() / "logs")

    def reload_env(self) -> dict[str, Any]:
        """Re-read .env (never written) and return only which keys are set."""
        from dodoclaw.webui import keycheck

        self._env_names = keycheck.reload_env_file(self._env_path, self._env_names)
        try:
            self._svc.reload_llm()
        except Exception:
            logger.exception("reload llm failed")
        self._last_test = {}
        self._coach_err = {}  # the key may have changed; the auto-test will report again
        return {"key": self._key_status(), "keys": keycheck.env_flags()}

    def test_key(self) -> dict[str, Any]:
        from dodoclaw.providers import chat_extra_body
        from dodoclaw.webui import keycheck

        c = self._svc.coach
        res = keycheck.test_key(
            c.api_key or "", c.base_url, c.model, extra_body=chat_extra_body(self._svc.provider_id, c.model)
        )
        self._last_test = {**res, "at": time.time()}
        if res.get("ok"):
            self._coach_err = {}
        elif res.get("kind") != "no_key":
            self._coach_err = {"kind": res["kind"], "reason_zh": res["reason_zh"], "at": time.time()}
        return res

    def open_key_page(self) -> bool:
        from dodoclaw.providers import get_provider

        url = get_provider(self._svc.provider_id).docs_url
        if not url.startswith("https://"):
            return False
        import webbrowser

        return bool(webbrowser.open(url))

    def set_tts(self, on: bool) -> dict[str, Any]:
        import importlib.util

        if on and importlib.util.find_spec("edge_tts") is None:
            return {"ok": False, "msg": "这个版本还没带 Edge 声音组件"}
        try:
            self._svc.reload_voice(tts_backend="edge" if on else "mock")
        except Exception:
            logger.exception("set tts failed")
            return {"ok": False, "msg": "播报没能启动，详情见日志"}
        return {"ok": (self._svc.tts_backend != "mock") == bool(on), "msg": ""}

    def preview_tts(self) -> dict[str, Any]:
        """试听 with Edge TTS, regardless of whether 语音播报 is on. Returns {ok, msg}."""
        from dodoclaw.webui import tts_preview

        try:
            return tts_preview.preview(tts_preview.edge_voice(getattr(self._svc, "tts_voice", "")))
        except Exception:
            logger.exception("tts preview failed")
            return {"ok": False, "msg": tts_preview.MSG_UNKNOWN}

    def rewrite_cfg(self) -> dict[str, Any]:
        from dodoclaw.gsi_install import install_gsi_cfg

        ok, msg, _dest = install_gsi_cfg()
        return {"ok": ok, "msg": "已重新写入，重启 Dota 后生效" if ok else "没找到 Dota 目录，详情见日志"}

    def set_gsi_record(self, on: bool) -> bool:
        if on and self._svc._recorder is None:
            from dodoclaw.gsi.recorder import GsiRecorder
            from dodoclaw.paths import app_dir

            self._svc._recorder = GsiRecorder(app_dir() / "logs" / "gsi")
        elif not on and self._svc._recorder is not None:
            rec, self._svc._recorder = self._svc._recorder, None
            try:
                rec.close()
            except Exception:
                logger.debug("recorder close", exc_info=True)
        return self._svc._recorder is not None

    def clear_icon_cache(self) -> int:
        n = 0
        root = self._icons.root
        if root.exists():
            for p in root.rglob("*.png"):
                try:
                    p.unlink()
                    n += 1
                except OSError:
                    pass
        self._icons._mem.clear()
        self._icons._failed.clear()
        return n

    def reset_overlay_pos(self) -> bool:
        if self._ov_win is None:
            return False
        self._ov_win.move(*OV_POS)
        return True

    def toggle_overlay(self) -> bool:
        shown = not (self.overlay_forced if self.overlay_forced is not None else False)
        self.overlay_forced = shown
        if self._ov_win:
            self._ov_win.show() if shown else self._ov_win.hide()
        return shown

    def fit_overlay(self, w: int, h: int) -> None:
        if self._ov_win is not None and 100 <= int(w) <= 800 and 40 <= int(h) <= 900:
            self._ov_win.resize(int(w), int(h))
            self._shape_overlay()

    def _shape_overlay(self) -> None:
        """Round the overlay's corners (Win11 DWM / Win10 window region). One-shot, not per frame."""
        if self._ov_win is None:
            return
        from dodoclaw.webui import winshape

        if self._ov_shape == "dwm":  # DWM keeps the corners through resizes
            return
        try:
            self._ov_shape = winshape.round_corners(winshape.hwnd_of(self._ov_win))
        except Exception:
            logger.debug("overlay corner shaping failed", exc_info=True)

    def toggle_compact(self) -> bool:
        self.compact = not self.compact
        if self._ov_win:
            w, h = OV_COMPACT if self.compact else (OV_W, OV_H)
            self._ov_win.resize(w, h)
            self._shape_overlay()
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
                want = self._svc.snapshot().in_game and bool(self.ui.get("auto_overlay", True))
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
        x=OV_POS[0],
        y=OV_POS[1],
        frameless=True,
        easy_drag=False,
        on_top=True,
        # Not transparent=True: on WinForms that leaves the Form's grey BackColor
        # around the card and EdgeChromium transparent windows get no input.
        resizable=False,
        hidden=True,
        focus=True,
        background_color=OV_BG,
    )
    bridge._main_win.events.closed += bridge.close
    bridge._ov_win.events.shown += bridge._shape_overlay
    bridge._ov_win.events.loaded += bridge._shape_overlay

    def _started() -> None:
        threading.Thread(target=bridge._watch, name="overlay-watch", daemon=True).start()

    webview.start(_started, gui="edgechromium" if os.name == "nt" else None,
                  http_server=True, debug=debug)
    return 0
