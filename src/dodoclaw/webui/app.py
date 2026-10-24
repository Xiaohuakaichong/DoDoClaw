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
STT_ZH = {"mock": "关", "whisper": "本地识别", "stepfun_plan": "云端识别", "stepfun": "云端识别", "siliconflow": "云端识别"}
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
        # pywebview's WinForms resize()/move() use SWP_SHOWWINDOW, so touching a
        # hidden overlay pops it up as an empty box: park size/pos until shown.
        self._ov_shown = False
        self._ov_pending_size: tuple[int, int] | None = None
        self._ov_pending_pos: tuple[int, int] | None = None
        self.reduce_motion = False
        self._busy = False
        self._answer: dict[str, Any] = {}
        self._alert: dict[str, Any] = {}
        self._error = ""
        self._coach_err: dict[str, Any] = {}  # {kind, reason_zh} of the last failed coach call
        self._last_ask_ms: int | None = None
        # settings page
        from dodoclaw.webui import keycheck, keystore, settings_store

        self._tts_ok: bool | None = None
        self._switched_from = ""  # provider we just switched away from (for “切回 …”)
        self._env_path = keystore.env_path()  # next to the exe, or the repo root from source
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
            "coach": {"provider": self._provider_label(), "model": svc.coach.model, "key_ok": key_ok, "error": coach_error},
            "voice": {
                "tts": svc.tts_backend,
                "stt": svc.stt_backend,
                "tts_zh": TTS_ZH.get(svc.tts_backend, "已配置"),
                "stt_zh": STT_ZH.get(svc.stt_backend, "已配置"),
                "tts_available": self._tts_available(),
            },
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
        from dodoclaw.webui import customs
        from dodoclaw.webui.keycheck import key_status

        c = self._svc.coach
        cid = customs.active_custom_id() if self._svc.provider_id == "custom" else ""
        return key_status(
            self._svc.provider_id,
            self._svc.provider_name,
            c.api_key or "",
            c.model or "",
            base_url=c.base_url or "",
            custom_id=cid,
        )

    def _provider_label(self) -> str:
        from dodoclaw.webui import keycheck

        return keycheck.provider_label(self._svc.provider_id)

    def _tts_available(self) -> bool:
        from dodoclaw.webui import tts_preview

        if getattr(self, "_tts_ok", None) is None:  # find_spec once per run; the package cannot appear later
            self._tts_ok = tts_preview.tts_available()
        return bool(self._tts_ok)

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
            # Missing component: UI greys the card (whisper_ready=False). Do not
            # toast over the option cards (design settings-voice-stt-missing).
            if importlib.util.find_spec("faster_whisper") is None:
                return "缺少本地识别组件"
            backend = "whisper"
        else:
            # Prefer SiliconFlow SenseVoice when that key is available; else 阶跃.
            if key.get("siliconflow_key"):
                backend = "siliconflow"
            elif key.get("stepfun_key"):
                backend = key["provider"] if key["provider"] in ("stepfun_plan", "stepfun") else "stepfun_plan"
            else:
                return "云端识别需要硅基流动或阶跃的 Key：先保存 Key，或把教练切到其中一家"
        try:
            self._svc.reload_voice(stt_backend=backend)
        except Exception:
            logger.exception("enable stt failed")
            return "语音识别没能启动，详情见日志"
        if self._svc.stt_backend == "mock":
            return "语音识别没能启动，详情见日志"
        return ""

    def _voice_state(self, key: dict[str, Any]) -> dict[str, Any]:
        import importlib.util

        from dodoclaw.webui import tts_preview
        from dodoclaw.webui import whisper_model

        svc = self._svc
        ready = importlib.util.find_spec("faster_whisper") is not None
        dl = whisper_model.status()
        cloud_share = ""
        if key.get("provider") == "siliconflow" and key.get("siliconflow_key"):
            cloud_share = "与教练共用硅基流动 Key"
        elif key.get("siliconflow_key"):
            cloud_share = "使用已保存的硅基流动 Key"
        elif key.get("stepfun_key"):
            cloud_share = "与教练共用阶跃 Key" if key.get("provider") in ("stepfun", "stepfun_plan") else "使用已保存的阶跃 Key"
        return {
            "ask_on": bool(self.ui["voice_ask"]) and svc.stt_backend != "mock",
            "stt_mode": self.ui.get("stt_mode") or self._stt_default(key),
            "stt_default": self._stt_default(key),
            "stt_zh": STT_ZH.get(svc.stt_backend, "已配置"),
            "whisper_ready": ready,
            "whisper_model_ready": bool(dl.get("ready")),
            "whisper_download": dl,
            "cloud_key_ready": bool(key.get("siliconflow_key") or key.get("stepfun_key")),
            "cloud_share_zh": cloud_share,
            "tts_on": svc.tts_backend != "mock",
            "tts_zh": TTS_ZH.get(svc.tts_backend, "已配置"),
            "preview_voice_zh": _preview_voice_zh(getattr(svc, "tts_voice", "")),
            # README D10 #coach,tts-missing: 声音 row says so up front; 试听 and the switch are disabled
            "tts_available": self._tts_available(),
            "tts_missing_zh": tts_preview.MSG_NO_EDGE_SHORT,
            "tts_missing_detail_zh": tts_preview.MSG_NO_EDGE_DETAIL,
        }

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
        return {
            "ui": self.ui,
            "budget": settings_store.budget(self.ui["reminders"]),
            "budget_cap": settings_store.BUDGET_CAP,
            "over_cap_hint": settings_store.OVER_CAP_HINT,
            "pending": sorted(settings_store.PENDING),
            "key": {**key, "last_test": self._last_test_view(), "switched_from": self._switched_view(key)},
            "providers": self.list_providers(),
            "customs": self.list_customs(),
            "voice": self._voice_state(key),
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
        # 小窗透明度 is gone (D11): the overlay window is opaque, a slider would do nothing.
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
        """Re-read .env into the process and return only which keys are set."""
        from dodoclaw.webui import keycheck

        self._env_names = keycheck.reload_env_file(self._env_path, self._env_names)
        try:
            self._svc.reload_llm()
        except Exception:
            logger.exception("reload llm failed")
        self._last_test = {}
        self._coach_err = {}  # the key may have changed; the auto-test will report again
        self._coach_gen = getattr(self, "_coach_gen", 0) + 1
        return {"key": self._key_status(), "keys": keycheck.env_flags()}

    def _reload_coach(self) -> None:
        try:
            self._svc.reload_llm()
        except Exception:
            logger.exception("reload llm failed")
        self._last_test = {}
        self._coach_err = {}
        self._coach_gen = getattr(self, "_coach_gen", 0) + 1

    def _follow_provider_stt(self) -> str:
        """Speech recognition left on 跟随服务商 (stt_mode unset) follows a provider/key
        change; a mode the user picked by hand is never changed."""
        if self.ui.get("voice_ask") and not self.ui.get("stt_mode"):
            return self._apply_stt(True)
        return ""

    def list_providers(self) -> list[dict[str, Any]]:
        """服务商 dropdown: the five presets with booleans only (README D10 js_api)."""
        from dodoclaw.webui import keycheck

        configured = bool((self._svc.coach.api_key or "").strip())
        return keycheck.list_providers(self._svc.provider_id, configured)

    def _last_test_view(self) -> dict[str, Any]:
        """Last 测试 result + the fixed Chinese next step for a failure."""
        from dodoclaw.webui import keycheck

        t = self._last_test
        if not t:
            return {}
        out = {k: t.get(k) for k in ("ok", "kind", "reason_zh", "ms", "model", "at")}
        if not t.get("ok"):
            out.update(keycheck.test_guide(str(t.get("kind") or "")))
        return out

    def _switched_view(self, key: dict[str, Any]) -> dict[str, Any] | None:
        """After switching to a provider without a key: the previous one, if it has one."""
        from dodoclaw.webui import keycheck, keystore

        pid = getattr(self, "_switched_from", "")
        if not pid or key["configured"] or pid == key["provider"]:
            return None
        from dodoclaw.providers import get_provider

        if not keystore.has_key(get_provider(pid).key_env):
            return None
        return {"id": pid, "name": keycheck.provider_label(pid)}

    def set_provider(self, provider_id: str) -> dict[str, Any]:
        """Select a provider: write coach.provider + coach.model (that provider's
        default model; base_url back to its default) and hot-reload the coach.
        Returns {ok, msg, provider, model, key: {configured}}."""
        from dodoclaw import config
        from dodoclaw.providers import get_provider
        from dodoclaw.webui import keycheck

        def out(ok: bool, msg: str = "") -> dict[str, Any]:
            return {
                "ok": ok,
                "msg": msg,
                "provider": self._svc.provider_id,
                "model": self._svc.coach.model,
                "key": {"configured": bool((self._svc.coach.api_key or "").strip())},
            }

        pid = str(provider_id or "")
        if pid == "__add_custom__":
            return out(False, "")  # UI opens the form; nothing to save
        if pid.startswith("custom:"):
            return self.select_custom(pid.split(":", 1)[1])
        if pid not in keycheck.PICKER_IDS:
            return out(False, "没有这个服务商")
        prev = self._svc.provider_id
        if pid == prev:
            return out(True)
        try:
            # Clear base_url override so the preset's fixed URL is used
            config.save_coach_choice(pid, get_provider(pid).default_model, "")
        except Exception:
            logger.exception("save coach provider failed")
            return out(False, "没能保存服务商选择，详情见日志")
        self._switched_from = prev
        self._reload_coach()
        msg = self._follow_provider_stt()
        self._save_ui()
        return out(True, msg)

    def save_key(self, provider_id: str, key: str) -> dict[str, Any]:
        """The only bridge method that receives a key (README D10).

        strip → KeyStore.set → reload → test_key. Save first, then test: a failed
        test keeps the key. Returns {ok, kind, reason_zh, ms, model, configured} —
        never the key; nothing here logs it or puts it in an error."""
        from dodoclaw.providers import get_provider
        from dodoclaw.webui import keystore

        pid = str(provider_id or "")
        if pid != self._svc.provider_id:
            # the dropdown changed while the key was being typed: never file it under another provider
            return self._key_fail("invalid", "服务商刚刚变了，请重新粘贴")
        from dodoclaw.webui import customs

        if pid == "custom":
            cp = customs.get_custom(customs.active_custom_id())
            if not cp:
                return self._key_fail("invalid", "请先保存自定义接口地址和模型")
            env_var, log_id = cp.key_env, f"custom:{cp.id}"
        else:
            spec = get_provider(pid)
            env_var, log_id = spec.key_env, spec.id
        try:
            keystore.save_key(env_var, key if isinstance(key, str) else "")
        except keystore.KeyStoreError as exc:
            return self._key_fail("store" if exc.reason_zh == keystore.MSG_WRITE else "invalid", exc.reason_zh)
        finally:
            key = ""  # drop our reference early
        logger.info("saved key for %s", log_id)
        self.reload_env()
        self._switched_from = ""
        res = self.test_key()
        stt_msg = self._follow_provider_stt()
        self._save_ui()
        return {
            "ok": bool(res.get("ok")),
            "kind": res.get("kind", ""),
            "reason_zh": res.get("reason_zh", ""),
            "ms": res.get("ms"),
            "model": res.get("model", ""),
            "configured": bool((self._svc.coach.api_key or "").strip()),
            "saved": True,
            "msg": stt_msg,
        }

    def delete_key(self, provider_id: str) -> dict[str, Any]:
        """更换 Key → 删除 Key (after the in-page confirm). Removes only the active
        line of that provider's variable from .env (no backup), reloads, clears the
        last test. Providers sharing the variable (阶跃 ×2) lose it too. Returns {ok, msg}."""
        from dodoclaw.providers import get_provider
        from dodoclaw.webui import keycheck, keystore

        pid = str(provider_id or "")
        from dodoclaw.webui import customs

        if pid != self._svc.provider_id:
            return {"ok": False, "msg": "服务商刚刚变了，请重新操作"}
        if pid == "custom":
            cp = customs.get_custom(customs.active_custom_id())
            if not cp:
                return {"ok": False, "msg": "没有这家自定义服务商"}
            env_var, log_id = cp.key_env, f"custom:{cp.id}"
        elif pid not in keycheck.PICKER_IDS:
            return {"ok": False, "msg": "服务商刚刚变了，请重新操作"}
        else:
            spec = get_provider(pid)
            env_var, log_id = spec.key_env, spec.id
        try:
            keystore.delete_key(env_var)
        except keystore.KeyStoreError as exc:
            return {"ok": False, "msg": exc.reason_zh}
        logger.info("deleted key for %s", log_id)
        self.reload_env()  # also clears last_test / coach error
        self._switched_from = ""
        msg = self._follow_provider_stt()
        self._save_ui()
        if (self._svc.coach.api_key or "").strip():
            # e.g. the generic LLM_API_KEY line or a system environment variable
            msg = "这一家的 Key 已删除，但还读到了通用 Key（LLM_API_KEY），教练仍能回答；要停用，请在 .env 里删掉那一行"
        return {"ok": True, "msg": msg}

    def _key_fail(self, kind: str, reason_zh: str) -> dict[str, Any]:
        return {
            "ok": False,
            "kind": kind,
            "reason_zh": reason_zh,
            "ms": None,
            "model": self._svc.coach.model,
            "configured": bool((self._svc.coach.api_key or "").strip()),
            "saved": False,
            "msg": "",
        }

    def test_key(self) -> dict[str, Any]:
        from dodoclaw.providers import chat_extra_body
        from dodoclaw.webui import keycheck

        c = self._svc.coach
        gen = getattr(self, "_coach_gen", 0)
        res = keycheck.test_key(
            c.api_key or "", c.base_url, c.model, extra_body=chat_extra_body(self._svc.provider_id, c.model)
        )
        res = {**res, "model": c.model}
        if gen != getattr(self, "_coach_gen", 0):
            # the provider or key changed while this request was out (fast switching):
            # the result belongs to the old choice, so it is not recorded
            return {**res, "stale": True}
        self._last_test = {**res, "at": time.time()}
        if res.get("ok"):
            self._coach_err = {}
        elif res.get("kind") != "no_key":
            self._coach_err = {"kind": res["kind"], "reason_zh": res["reason_zh"], "at": time.time()}
        return res


    def list_customs(self) -> list[dict]:
        """Saved custom OpenAI-compatible providers (booleans only)."""
        from dodoclaw.webui import customs

        cur = customs.active_custom_id() if self._svc.provider_id == "custom" else ""
        return customs.public_list(current_id=cur)

    def save_custom(
        self,
        name: str = "",
        base_url: str = "",
        model: str = "",
        key: str = "",
        custom_id: str = "",
    ) -> dict:
        """Create/update a custom provider, optionally save its Key, then test.

        Returns {ok, kind, reason_zh, ms, model, configured, custom_id, field} —
        never the key. ``field`` is url|model|key|"" for inline form errors.
        """
        from dodoclaw.webui import customs, keystore
        from dodoclaw.webui.provider_validate import MSG_MODEL_EMPTY, MSG_URL_EMPTY

        def fail(kind: str, reason_zh: str, field: str = "") -> dict:
            return {
                "ok": False,
                "kind": kind,
                "reason_zh": reason_zh,
                "ms": None,
                "model": model or "",
                "configured": False,
                "saved": False,
                "custom_id": custom_id or "",
                "field": field,
                "msg": "",
            }

        try:
            entry = customs.save_custom(
                name=name or "",
                base_url=base_url or "",
                model=model or "",
                custom_id=custom_id or "",
                activate=True,
            )
        except ValueError as exc:
            msg = str(exc)
            field = "url"
            if "模型" in msg:
                field = "model"
            elif "名称" in msg:
                field = "name"
            return fail("invalid", msg, field)
        except Exception:
            logger.exception("save custom failed")
            return fail("store", "没能保存自定义服务商，详情见日志")

        if isinstance(key, str) and key.strip():
            try:
                keystore.save_key(entry.key_env, key)
            except keystore.KeyStoreError as exc:
                field = "key"
                return {**fail("invalid", exc.reason_zh, field), "custom_id": entry.id, "saved": False}
            finally:
                key = ""
        self._switched_from = ""
        self._reload_coach()
        res = self.test_key()
        # Map test failure kinds onto form fields (design D12 inline errors)
        field = ""
        if not res.get("ok"):
            kind = res.get("kind") or ""
            if kind in ("bad_address", "network"):
                field = "url"
                if kind == "bad_address":
                    res = {**res, "reason_zh": "地址连不上 · 检查 URL 或网络后重试"}
            elif kind == "auth":
                field = "key"
                res = {**res, "reason_zh": "Key 无效 · 可能复制少了一截，或在平台上被删了"}
            elif kind == "not_found":
                field = "model"
                res = {**res, "reason_zh": "模型不存在 · 核对平台上的模型 ID"}
        stt_msg = self._follow_provider_stt()
        self._save_ui()
        return {
            "ok": bool(res.get("ok")),
            "kind": res.get("kind", ""),
            "reason_zh": res.get("reason_zh", ""),
            "ms": res.get("ms"),
            "model": entry.model,
            "configured": bool((self._svc.coach.api_key or "").strip()),
            "saved": True,
            "custom_id": entry.id,
            "field": field,
            "msg": stt_msg,
        }

    def delete_custom(self, custom_id: str) -> dict:
        """Delete one custom provider and its Key. Returns {ok, msg}."""
        from dodoclaw.webui import customs, keystore

        removed = customs.delete_custom(str(custom_id or ""))
        if not removed:
            return {"ok": False, "msg": customs.MSG_NOT_FOUND}
        try:
            if keystore.has_key(removed.key_env):
                keystore.delete_key(removed.key_env)
        except keystore.KeyStoreError as exc:
            return {"ok": False, "msg": exc.reason_zh}
        self._reload_coach()
        msg = self._follow_provider_stt()
        self._save_ui()
        return {"ok": True, "msg": msg}

    def select_custom(self, custom_id: str) -> dict:
        """Make a saved custom provider the current coach."""
        from dodoclaw.webui import customs

        def out(ok: bool, msg: str = "") -> dict:
            return {
                "ok": ok,
                "msg": msg,
                "provider": self._svc.provider_id,
                "model": self._svc.coach.model,
                "key": {"configured": bool((self._svc.coach.api_key or "").strip())},
            }

        try:
            customs.select_custom(str(custom_id or ""))
        except ValueError as exc:
            return out(False, str(exc))
        except Exception:
            logger.exception("select custom failed")
            return out(False, "没能切换自定义服务商，详情见日志")
        prev = self._svc.provider_id
        self._switched_from = prev
        self._reload_coach()
        msg = self._follow_provider_stt()
        self._save_ui()
        return out(True, msg)

    def save_coach_model(self, model: str = "") -> dict:
        """Override the current preset's model (hand-editable combobox). Empty = default."""
        from dodoclaw import config
        from dodoclaw.providers import get_provider
        from dodoclaw.webui.provider_validate import validate_model_id

        pid = self._svc.provider_id
        if pid == "custom":
            return {"ok": False, "msg": "自定义服务商请用保存自定义接口"}
        try:
            mdl = validate_model_id(model) if (model or "").strip() else ""
        except ValueError as exc:
            return {"ok": False, "msg": str(exc)}
        spec = get_provider(pid)
        if not mdl or mdl == spec.default_model:
            mdl = ""  # remove override
        try:
            config.save_coach_choice(pid, mdl, "")
        except Exception:
            logger.exception("save coach model failed")
            return {"ok": False, "msg": "没能保存模型，详情见日志"}
        self._reload_coach()
        return {"ok": True, "msg": "", "model": self._svc.coach.model, "default_model": spec.default_model}

    def whisper_status(self) -> dict:
        from dodoclaw.webui import whisper_model

        return whisper_model.status()

    def start_whisper_download(self) -> dict:
        from dodoclaw.webui import whisper_model

        return whisper_model.start_download()

    def cancel_whisper_download(self) -> dict:
        from dodoclaw.webui import whisper_model

        return whisper_model.cancel_download()

    def open_key_page(self, provider_id: str = "", purpose: str = "key") -> bool:
        """去申请 (key page) / 去充值 · 去续订 (purpose="topup"). https only."""
        from dodoclaw.providers import PROVIDERS, get_provider

        pid = provider_id if provider_id in PROVIDERS else self._svc.provider_id
        spec = get_provider(pid)
        url = spec.topup_url() if purpose == "topup" else spec.apply_url()
        if not url.startswith("https://"):
            return False
        import webbrowser

        return bool(webbrowser.open(url))

    def set_tts(self, on: bool) -> dict[str, Any]:
        if on and not self._tts_available():
            return {"ok": False, "msg": "缺少声音组件，换最新安装包即可恢复"}
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

    # Every overlay window call (show/hide/move/resize/shape/topmost) goes through
    # this one lock, so JS-api threads, the watch thread and pywebview events never
    # touch the window at the same time. Class-level so tests' Bridge.__new__ has it.
    _ov_lock = threading.RLock()

    def reset_overlay_pos(self) -> bool:
        if self._ov_win is None:
            return False
        with self._ov_lock:
            if self._ov_shown:
                self._ov_win.move(*OV_POS)
            else:
                self._ov_pending_pos = OV_POS
        return True

    def toggle_overlay(self) -> bool:
        with self._ov_lock:
            shown = not (self.overlay_forced if self.overlay_forced is not None else False)
            self.overlay_forced = shown
            self._set_overlay_visible(shown)
        return shown

    def _set_overlay_visible(self, want: bool) -> None:
        if self._ov_win is None:
            return
        with self._ov_lock:
            self._set_overlay_visible_locked(want)

    def _set_overlay_visible_locked(self, want: bool) -> None:
        if not want:
            self._ov_shown = False
            self._ov_win.hide()
            return
        self._ov_win.show()
        self._ov_shown = True
        pos, self._ov_pending_pos = self._ov_pending_pos, None
        size, self._ov_pending_size = self._ov_pending_size, None
        if pos:
            self._ov_win.move(*pos)
        if size:
            self._resize_overlay(*size)

    def _resize_overlay(self, w: int, h: int) -> None:
        with self._ov_lock:
            if not self._ov_shown:
                self._ov_pending_size = (w, h)
                return
            self._ov_win.resize(w, h)
            self._shape_overlay()

    def fit_overlay(self, w: int, h: int) -> None:
        if self._ov_win is not None and 100 <= int(w) <= 800 and 40 <= int(h) <= 900:
            self._resize_overlay(int(w), int(h))

    def _shape_overlay(self) -> None:
        """Round the overlay's corners (Win11 DWM / Win10 window region). One-shot, not per frame."""
        if self._ov_win is None:
            return
        from dodoclaw.webui import winshape

        if self._ov_shape == "dwm":  # DWM keeps the corners through resizes
            return
        with self._ov_lock:
            try:
                self._ov_shape = winshape.round_corners(winshape.hwnd_of(self._ov_win))
            except Exception:
                logger.debug("overlay corner shaping failed", exc_info=True)

    def toggle_compact(self) -> bool:
        with self._ov_lock:
            self.compact = not self.compact
            if self._ov_win:
                self._resize_overlay(*(OV_COMPACT if self.compact else (OV_W, OV_H)))
            return self.compact

    def _keep_overlay_on_top(self) -> None:
        """Re-assert topmost without pywebview's ``on_top`` setter.

        ``window.on_top = True`` sets the WinForms ``TopMost`` property from this
        worker thread. pythonnet keeps the GIL during property sets, and TopMost
        calls SetWindowPos, which waits for the UI thread; if the UI thread is in
        a resize/move handler that needs the GIL (pywebview's on_resize/on_move),
        both wait forever and the app freezes (seen on compact/expand). A ctypes
        SetWindowPos releases the GIL while it waits.
        """
        from dodoclaw.webui import winshape

        with self._ov_lock:
            if self._ov_win is not None and self._ov_shown:
                winshape.keep_on_top(winshape.hwnd_of(self._ov_win))

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
        while True:
            time.sleep(2.0)
            try:
                want = self._svc.snapshot().in_game and bool(self.ui.get("auto_overlay", True))
                if self.overlay_forced is not None:
                    want = self.overlay_forced
                if self._ov_win and want != self._ov_shown:
                    self._set_overlay_visible(want)
                if self._ov_win and self._ov_shown:
                    self._keep_overlay_on_top()
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
        min_size=(100, 40),  # pywebview's default 200x100 kept the compact pill window 100px tall
        hidden=True,
        focus=True,
        background_color=OV_BG,
    )
    bridge._main_win.events.closed += bridge.close
    bridge._ov_win.events.shown += bridge._shape_overlay
    bridge._ov_win.events.loaded += bridge._shape_overlay

    def _started() -> None:
        threading.Thread(target=bridge._watch, name="overlay-watch", daemon=True).start()
        # If the window thread ever stops answering, dump every thread's stack to
        # logs/hang.log next to the exe (so a freeze on a user's PC is diagnosable).
        from dodoclaw.paths import app_dir
        from dodoclaw.webui import winshape
        from dodoclaw.webui.hangwatch import HangWatch

        HangWatch(app_dir() / "logs" / "hang.log", lambda: winshape.hwnd_of(bridge._main_win)).start()

    webview.start(_started, gui="edgechromium" if os.name == "nt" else None,
                  http_server=True, debug=debug)
    return 0
