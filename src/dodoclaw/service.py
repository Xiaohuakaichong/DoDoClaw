from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from dodoclaw.audio_providers import get_stt_backend, get_tts_backend
from dodoclaw.coach.agent import CoachAgent
from dodoclaw.config import get_settings, reload_settings
from dodoclaw.gsi.server import GSIServer
from dodoclaw.gsi.state import GameSnapshot, GameStateStore
from dodoclaw.providers import get_provider, resolve_llm_runtime
from dodoclaw.reminders.engine import ReminderEngine, ReminderEvent
from dodoclaw.voice.stt import create_stt
from dodoclaw.voice.tts import create_tts

logger = logging.getLogger(__name__)

LogFn = Callable[[str, str], None]  # level, message
ReminderFn = Callable[[ReminderEvent], None]
GsiFn = Callable[[GameSnapshot], None]


class DoDoClawService:
    """Headless core used by CLI and desktop GUI."""

    def __init__(
        self,
        on_log: LogFn | None = None,
        on_reminder: ReminderFn | None = None,
        on_gsi: GsiFn | None = None,
    ) -> None:
        self.on_log = on_log or (lambda _lvl, _msg: None)
        self.on_reminder_cb = on_reminder
        self.on_gsi_cb = on_gsi

        self.settings = get_settings()
        self.yaml = self.settings.load_yaml()
        self.store = GameStateStore()
        self._stop = threading.Event()
        self._started = False
        self._rem_thread: threading.Thread | None = None

        gsi_cfg = self.yaml.get("gsi") or {}
        self.gsi = GSIServer(
            store=self.store,
            host=self.settings.gsi_host or gsi_cfg.get("host", "127.0.0.1"),
            port=int(self.settings.gsi_port or gsi_cfg.get("port", 3000)),
            auth_token=self.settings.gsi_auth_token
            or gsi_cfg.get("auth_token", "dodoclaw_secret"),
            on_update=self._on_gsi,
        )

        coach_cfg = self.yaml.get("coach") or {}
        pid, pname, api_key, base_url, model = self.settings.resolve_llm()
        self.provider_id = pid
        self.provider_name = pname
        self.coach = CoachAgent(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt=(coach_cfg.get("system_style") or None),
            max_reply_chars=int(coach_cfg.get("max_reply_chars") or 280),
            provider_id=pid,
            provider_name=pname,
        )

        voice_cfg = self.yaml.get("voice") or {}
        self.record_seconds = float(voice_cfg.get("record_seconds") or 5)
        self.stt_backend = self.settings.stt_backend or voice_cfg.get("stt_backend", "mock")
        self.tts_backend = self.settings.tts_backend or voice_cfg.get("tts_backend", "mock")
        self.stt_model = self.settings.stt_model or str(voice_cfg.get("stt_model") or "")
        self.tts_model = self.settings.tts_model or str(voice_cfg.get("tts_model") or "")
        self.tts_voice = self.settings.tts_voice or str(voice_cfg.get("tts_voice") or "")
        self.stt, self.tts = self._build_voice_stack()

        rem_cfg = self.yaml.get("reminders") or {}
        self.reminders_enabled = bool(rem_cfg.get("enabled", True))
        self.reminders = ReminderEngine(
            store=self.store,
            cooldown_sec=float(rem_cfg.get("cooldown_sec") or 25),
            announce_ult_ready=bool(rem_cfg.get("announce_ult_ready", False)),
            on_reminder=self._on_reminder,
        )

        # BP / meta (OpenDota and/or STRATZ — user-owned tokens recommended)
        meta_cfg = self.yaml.get("meta") or {}
        self.meta_enabled = bool(meta_cfg.get("enabled", True))
        self.meta_source = (
            self.settings.meta_source
            or str(meta_cfg.get("source") or "auto")
        ).strip().lower()
        self._draft_advisor = None
        if self.meta_enabled:
            self._init_draft_advisor(meta_cfg)

        # Patch + hero mechanics knowledge base
        kb_cfg = self.yaml.get("knowledge") or {}
        self.knowledge_enabled = bool(kb_cfg.get("enabled", True))
        self._knowledge = None
        if self.knowledge_enabled:
            try:
                from dodoclaw.knowledge.base import KnowledgeBase

                self._knowledge = KnowledgeBase(
                    language=str(kb_cfg.get("language") or "schinese"),
                    patch_last_n=int(kb_cfg.get("patch_last_n") or 3),
                    ttl_sec=int(kb_cfg.get("ttl_sec") or 24 * 3600),
                )
                # lazy sync on first ask; optional warm load of cache
                self._knowledge.load()
            except Exception:
                logger.exception("knowledge base init failed")
                self._knowledge = None

        self._gsi_updates = 0
        self._recorder = None
        if self.settings.gsi_record:
            from dodoclaw.gsi.recorder import GsiRecorder
            from dodoclaw.paths import app_dir

            self._recorder = GsiRecorder(app_dir() / "logs" / "gsi")
            self._log("info", f"GSI 采样已开启: {app_dir() / 'logs' / 'gsi'}")

    def _init_draft_advisor(self, meta_cfg: dict[str, Any] | None = None) -> None:
        meta_cfg = meta_cfg or (self.yaml.get("meta") or {})
        try:
            from dodoclaw.meta.draft import DraftAdvisor
            from dodoclaw.meta.factory import create_meta_provider

            client = create_meta_provider(
                self.meta_source,
                opendota_api_key=self.settings.opendota_api_key
                or str(meta_cfg.get("opendota_api_key") or ""),
                stratz_api_token=self.settings.stratz_api_token
                or str(meta_cfg.get("stratz_api_token") or ""),
                cache_ttl_sec=int(meta_cfg.get("cache_ttl_sec") or 6 * 3600),
                opendota_bracket=int(
                    self.settings.opendota_bracket
                    or meta_cfg.get("opendota_bracket")
                    or 0
                ),
                stratz_bracket=str(
                    self.settings.stratz_bracket
                    or meta_cfg.get("stratz_bracket")
                    or "high"
                ),
                fallback_opendota=bool(meta_cfg.get("fallback_opendota", True)),
            )
            self._draft_advisor = DraftAdvisor(client)
            self._log(
                "info",
                f"BP Meta 已加载: {getattr(client, 'source_name', type(client).__name__)}",
            )
        except Exception as exc:
            logger.exception("draft advisor init failed")
            self._draft_advisor = None
            try:
                self._log("warning", f"BP Meta 未启用: {exc}")
            except Exception:
                pass

    def reload_meta(
        self,
        *,
        source: str | None = None,
        stratz_token: str | None = None,
        opendota_key: str | None = None,
        stratz_bracket: str | None = None,
    ) -> None:
        """Hot-reload meta provider (e.g. after user saves STRATZ token)."""
        self.settings = reload_settings()
        if source is not None:
            self.meta_source = source.strip().lower()
        meta_cfg = dict(self.yaml.get("meta") or {})
        if stratz_token is not None:
            # temporary override via env for this process
            import os

            os.environ["STRATZ_API_TOKEN"] = stratz_token
            self.settings = reload_settings()
        if opendota_key is not None:
            import os

            os.environ["OPENDOTA_API_KEY"] = opendota_key
            self.settings = reload_settings()
        if stratz_bracket is not None:
            import os

            os.environ["STRATZ_BRACKET"] = stratz_bracket
            self.settings = reload_settings()
        self._init_draft_advisor(meta_cfg)

    def _audio_credentials(self, backend_id: str) -> tuple[str, str]:
        """Resolve (api_key, base_url) for a StepFun-style audio backend."""
        spec_stt = get_stt_backend(backend_id)
        spec_tts = get_tts_backend(backend_id)
        # prefer matching llm provider keys
        linked = (
            getattr(spec_stt, "key_from_llm_provider", "")
            or getattr(spec_tts, "key_from_llm_provider", "")
            or backend_id
        )
        if backend_id in {"stepfun_plan", "stepfun"}:
            linked = backend_id
        _spec, key, url, _model = resolve_llm_runtime(
            linked if linked in {"stepfun_plan", "stepfun"} else self.provider_id,
            api_key=self.settings.llm_api_key or self.settings.stepfun_api_key,
            base_url="",
            model="",
        )
        # force audio base from audio backend when stepfun*
        if backend_id == "stepfun_plan":
            url = get_stt_backend("stepfun_plan").base_url or url
            key = key or self.settings.stepfun_api_key or self.settings.llm_api_key
        elif backend_id == "stepfun":
            url = get_stt_backend("stepfun").base_url or url
            key = key or self.settings.stepfun_api_key or self.settings.llm_api_key
        return key, url

    def _build_voice_stack(self):
        stt_key, stt_url = self._audio_credentials(self.stt_backend)
        tts_key, tts_url = self._audio_credentials(self.tts_backend)
        try:
            stt = create_stt(
                self.stt_backend,
                api_key=stt_key,
                base_url=stt_url,
                model=self.stt_model,
            )
        except Exception as exc:
            logger.warning("STT backend %s failed (%s); fallback mock", self.stt_backend, exc)
            stt = create_stt("mock")
        try:
            tts = create_tts(
                self.tts_backend,
                api_key=tts_key,
                base_url=tts_url,
                model=self.tts_model,
                voice=self.tts_voice,
            )
        except Exception as exc:
            logger.warning("TTS backend %s failed (%s); fallback mock", self.tts_backend, exc)
            tts = create_tts("mock")
        return stt, tts

    def reload_voice(
        self,
        *,
        stt_backend: str | None = None,
        tts_backend: str | None = None,
        stt_model: str | None = None,
        tts_model: str | None = None,
        tts_voice: str | None = None,
    ) -> None:
        self.settings = reload_settings()
        if stt_backend is not None:
            self.stt_backend = stt_backend
        if tts_backend is not None:
            self.tts_backend = tts_backend
        if stt_model is not None:
            self.stt_model = stt_model
        if tts_model is not None:
            self.tts_model = tts_model
        if tts_voice is not None:
            self.tts_voice = tts_voice
        try:
            self.stt, self.tts = self._build_voice_stack()
            self._log(
                "info",
                f"语音栈已更新 STT={self.stt_backend}({self.stt_model or '-'}) "
                f"TTS={self.tts_backend}({self.tts_model or self.tts_voice or '-'})",
            )
        except Exception as exc:
            self._log("error", f"语音栈加载失败: {exc}")
            raise

    def _log(self, level: str, msg: str) -> None:
        getattr(logger, level.lower(), logger.info)(msg)
        try:
            self.on_log(level, msg)
        except Exception:
            logger.exception("on_log failed")

    def _on_gsi(self, payload: dict[str, Any]) -> None:
        self._gsi_updates += 1
        if self._recorder is not None:
            self._recorder.record(payload)
        snap = self.store.get()
        if self._gsi_updates == 1:
            self._log("info", "已收到首包 GSI 数据")
        if self.on_gsi_cb:
            try:
                self.on_gsi_cb(snap)
            except Exception:
                logger.exception("on_gsi failed")

    def _on_reminder(self, event: ReminderEvent) -> None:
        self._log("info", f"提醒: {event.message}")
        if self.on_reminder_cb:
            try:
                self.on_reminder_cb(event)
            except Exception:
                logger.exception("on_reminder_cb failed")
        try:
            self.tts.speak(event.message)
        except Exception:
            logger.exception("TTS reminder failed")

    def _reminder_loop(self) -> None:
        while not self._stop.is_set():
            if self.reminders_enabled:
                try:
                    self.reminders.tick()
                except Exception:
                    logger.exception("reminder tick failed")
            self._stop.wait(0.5)

    @property
    def running(self) -> bool:
        return self._started and not self._stop.is_set()

    @property
    def gsi_update_count(self) -> int:
        return self.store.update_count

    def start(self) -> None:
        if self._started:
            return
        self._stop.clear()
        self.gsi.start()
        self._rem_thread = threading.Thread(
            target=self._reminder_loop, name="reminders", daemon=True
        )
        self._rem_thread.start()
        self._started = True
        self._log(
            "info",
            f"服务已启动 | GSI http://{self.gsi.host}:{self.gsi.port}/ | "
            f"LLM={self.provider_name} ({self.coach.model}) | "
            f"STT={self.stt_backend} TTS={self.tts_backend}",
        )

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self.gsi.stop()
        if self._recorder is not None:
            self._recorder.close()
        time.sleep(0.2)
        self._started = False
        self._log("info", "服务已停止")

    def reload_llm(
        self,
        *,
        provider_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        """Hot-reload provider / key / model on the coach client."""
        self.settings = reload_settings()
        pid = provider_id or self.settings.llm_provider or self.provider_id
        spec = get_provider(pid)
        pid, pname, key, url, mdl = self.settings.resolve_llm()
        if provider_id:
            spec = get_provider(provider_id)
            pid, pname = spec.id, spec.name
            # re-resolve with forced provider
            from dodoclaw.providers import resolve_llm_runtime

            _, key2, url2, mdl2 = resolve_llm_runtime(
                pid,
                api_key=api_key or self.settings.llm_api_key,
                base_url=base_url or self.settings.llm_base_url,
                model=model or self.settings.llm_model,
            )
            key, url, mdl = key2, url2, mdl2
            if api_key:
                key = api_key
            if base_url:
                url = base_url.rstrip("/")
            if model:
                mdl = model
        else:
            if api_key:
                key = api_key
            if base_url:
                url = base_url.rstrip("/")
            if model:
                mdl = model

        self.provider_id = pid
        self.provider_name = pname
        self.coach.configure(
            api_key=key,
            base_url=url,
            model=mdl,
            provider_id=pid,
            provider_name=pname,
        )
        self._log("info", f"LLM 已切换: {pname} / {mdl} @ {url}")

    def reload_api_key(self, api_key: str) -> None:
        self.reload_llm(api_key=api_key)

    def sync_llm_from_ui(
        self,
        *,
        provider_id: str,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        """Lightweight sync without rebuilding voice stack (safe before each ask)."""
        from dodoclaw.providers import get_provider

        spec = get_provider(provider_id)
        key = (api_key or "").strip()
        url = (base_url or "").strip() or spec.base_url
        mdl = (model or "").strip() or spec.default_model
        if (
            self.coach.api_key == key
            and self.coach.base_url.rstrip("/") == url.rstrip("/")
            and self.coach.model == mdl
            and self.provider_id == spec.id
        ):
            return
        self.provider_id = spec.id
        self.provider_name = spec.name
        self.coach.configure(
            api_key=key,
            base_url=url,
            model=mdl,
            provider_id=spec.id,
            provider_name=spec.name,
        )
        logger.info("LLM sync: %s / %s", spec.name, mdl)

    def snapshot(self) -> GameSnapshot:
        return self.store.get()

    def status_text(self) -> str:
        snap = self.snapshot()
        return (
            f"{snap.summary_for_llm()}\n\n"
            f"GSI 包计数: {self.store.update_count}\n"
            f"服务: {'运行中' if self.running else '未启动'}\n"
            f"LLM: {self.provider_name}\n"
            f"Model: {self.coach.model}\n"
            f"Base: {self.coach.base_url}\n"
            f"BP Meta: "
            f"{(self._draft_advisor.source_name if self._draft_advisor else '关闭')}"
            f" (source={self.meta_source})"
        )

    def _draft_context_for(self, snap: GameSnapshot, question: str) -> str:
        if not self._draft_advisor:
            return ""
        q = question.lower()
        bp_keywords = (
            "bp",
            "ban",
            "pick",
            "禁",
            "选人",
            "选什么",
            "ban谁",
            "禁谁",
            "draft",
            "阵容",
            "对位",
            "克制",
            "版本",
            "meta",
            "热门",
        )
        want = snap.is_draft_phase or any(k in q for k in bp_keywords)
        if not want:
            # light meta brief still helps mid-game "版本" questions less often
            return ""
        try:
            return self._draft_advisor.build_advice(snap)
        except Exception as exc:
            logger.exception("draft advice failed")
            return f"BP 数据获取失败: {exc}"

    def draft_advice(self, speak: bool = False) -> str:
        """Force-generate BP / meta advice from current GSI + OpenDota/STRATZ."""
        if not self._draft_advisor:
            return (
                "BP Meta 未启用。\n"
                "· OpenDota：无需 Token（默认）\n"
                "· STRATZ：在设置填写 STRATZ_API_TOKEN（https://stratz.com/api）\n"
                "· META_SOURCE=auto|opendota|stratz"
            )
        snap = self.snapshot()
        text = self._draft_advisor.build_advice(snap)
        self._log("info", "已生成 BP 指导")
        if speak:
            try:
                # short spoken summary via LLM if key present, else first lines
                if self.coach.api_key:
                    spoken = self.coach.answer(
                        "根据 BP/Meta 参考，用两句话告诉我现在该禁或选什么。",
                        snap,
                        draft_context=text,
                    )
                    self.tts.speak(spoken)
                    return spoken
                self.tts.speak("已生成 BP 数据，请看聊天窗口。")
            except Exception:
                logger.exception("draft speak failed")
        return text

    def _knowledge_context(self, question: str, snap) -> str:
        if not self._knowledge:
            return ""
        hero_keys: list[str] = []
        if snap.hero_name:
            hero_keys.append(snap.hero_name)
        # also pull from abilities item names lightly via question only
        try:
            kb_cfg = self.yaml.get("knowledge") or {}
            return self._knowledge.context_for(
                question,
                hero_keys=hero_keys,
                top_k=int(kb_cfg.get("top_k") or 6),
                max_chars=int(kb_cfg.get("max_chars") or 2800),
            )
        except Exception:
            logger.exception("knowledge retrieve failed")
            return ""

    def sync_knowledge(self, *, force: bool = True) -> dict:
        if not self._knowledge:
            from dodoclaw.knowledge.base import KnowledgeBase

            self._knowledge = KnowledgeBase()
            self.knowledge_enabled = True
        return self._knowledge.sync(force=force)

    def ask(self, question: str, speak: bool = True) -> str:
        question = (question or "").strip()
        if not question:
            return ""
        snap = self.snapshot()
        # Do not push Q/A into on_log — GUI already renders chat bubbles (avoids double messages)
        logger.info("ask: %s", question[:120])
        # Only pull heavy BP meta when relevant (avoid hanging casual chat)
        draft_ctx = self._draft_context_for(snap, question)
        knowledge_ctx = self._knowledge_context(question, snap)
        try:
            key = (self.coach.api_key or "").strip()
            if not key:
                self.settings = reload_settings()
                _pid, _pn, key, url, model = self.settings.resolve_llm()
                if key:
                    self.coach.configure(api_key=key, base_url=url, model=model)
            if (self.coach.api_key or "").strip():
                answer = self.coach.answer(
                    question,
                    snap,
                    draft_context=draft_ctx,
                    knowledge_context=knowledge_ctx,
                )
            else:
                answer = self.coach.answer_offline_fallback(question, snap)
                if knowledge_ctx:
                    answer = answer + "\n\n" + knowledge_ctx[:1200]
                if draft_ctx:
                    answer = answer + "\n\n" + draft_ctx[:800]
        except Exception as exc:
            logger.exception("coach failed")
            answer = f"教练调用失败: {exc}"

        logger.info("answer: %s", (answer or "")[:160])
        if speak and answer:
            # Never block the reply path too long — TTS is best-effort
            try:
                self.tts.speak(answer)
            except Exception as exc:
                logger.exception("TTS answer failed")
                self._log("warning", f"TTS 播报失败（文字回复仍有效）: {exc}")
        return answer

    def listen_once(self) -> str:
        return self.stt.listen_once(self.record_seconds)
