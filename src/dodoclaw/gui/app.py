from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from dodoclaw import __version__
from dodoclaw.audio_providers import (
    get_stt_backend,
    get_tts_backend,
    list_stt_backends,
    list_tts_backends,
)
from dodoclaw.config import get_settings, save_env_values
from dodoclaw.gsi_install import install_gsi_cfg
from dodoclaw.providers import (
    DEFAULT_PROVIDER_ID,
    get_provider,
    list_providers,
    provider_id_from_name,
)
from dodoclaw.service import DoDoClawService

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT = "#c23c2a"
ACCENT_HOVER = "#a33224"
PANEL = "#1a1d24"
PANEL2 = "#22262f"
TEXT_MUTED = "#9aa3b2"


class DoDoClawDesktop(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DoDoClaw  ·  Dota 2 语音助手  v{__version__}")
        self.geometry("1040x720")
        self.minsize(920, 600)
        self.configure(fg_color="#12141a")

        self._ui_queue: queue.Queue = queue.Queue()
        self._service: DoDoClawService | None = None
        self._busy = False
        self._providers = list_providers()
        self._provider_names = [p.name for p in self._providers]
        self._stt_backends = list_stt_backends()
        self._tts_backends = list_tts_backends()
        self._stt_names = [b.name for b in self._stt_backends]
        self._tts_names = [b.name for b in self._tts_backends]
        self._stt_name_to_id = {b.name: b.id for b in self._stt_backends}
        self._tts_name_to_id = {b.name: b.id for b in self._tts_backends}
        self._stt_id_to_name = {b.id: b.name for b in self._stt_backends}
        self._tts_id_to_name = {b.id: b.name for b in self._tts_backends}

        self._build_layout()
        self._load_settings_into_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(120, self._poll_ui_queue)
        self.after(1000, self._refresh_status_loop)

        self._append_system(
            "欢迎使用 DoDoClaw。建议：① 选择国内 Provider（默认 Step Plan）→ ② 填 Key → "
            "③ 安装 GSI → ④ 启动服务 → ⑤ 进对局提问。"
        )

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Scrollable sidebar for provider settings
        side = ctk.CTkScrollableFrame(self, width=300, corner_radius=0, fg_color=PANEL)
        side.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(
            side, text="🦀 DoDoClaw", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(padx=16, pady=(16, 4), anchor="w")
        ctk.CTkLabel(
            side,
            text="Dota 2 语音教练 · 社区版",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
        ).pack(padx=16, pady=(0, 12), anchor="w")

        self.status_dot = ctk.CTkLabel(
            side,
            text="●  服务未启动",
            text_color="#e5a84b",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.status_dot.pack(padx=16, pady=(0, 6), anchor="w")

        self.gsi_label = ctk.CTkLabel(
            side,
            text="GSI: 等待数据…",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=260,
        )
        self.gsi_label.pack(padx=16, pady=(0, 12), anchor="w")

        self.btn_start = ctk.CTkButton(
            side,
            text="启动服务",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            height=36,
            command=self._toggle_service,
        )
        self.btn_start.pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            side,
            text="安装 Dota GSI 配置",
            fg_color=PANEL2,
            hover_color="#2c3340",
            height=32,
            command=self._install_gsi,
        ).pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            side,
            text="查看当前局势",
            fg_color=PANEL2,
            hover_color="#2c3340",
            height=32,
            command=self._show_status,
        ).pack(padx=16, pady=4, fill="x")

        ctk.CTkButton(
            side,
            text="BP / Meta 指导",
            fg_color=PANEL2,
            hover_color="#2c3340",
            height=32,
            command=self._show_draft,
        ).pack(padx=16, pady=4, fill="x")

        # ── LLM provider ──
        ctk.CTkLabel(
            side,
            text="LLM Provider",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=16, pady=(18, 4), anchor="w")

        self.provider_menu = ctk.CTkOptionMenu(
            side,
            values=self._provider_names,
            command=self._on_provider_changed,
            fg_color=PANEL2,
            button_color="#2c3340",
            button_hover_color="#3a4252",
            height=32,
        )
        self.provider_menu.pack(padx=16, pady=4, fill="x")

        self.provider_note = ctk.CTkLabel(
            side,
            text="",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
        )
        self.provider_note.pack(padx=16, pady=(2, 6), anchor="w")

        ctk.CTkLabel(side, text="模型", text_color=TEXT_MUTED).pack(
            padx=16, pady=(4, 2), anchor="w"
        )
        self.model_menu = ctk.CTkComboBox(
            side,
            values=["step-3.7-flash"],
            height=32,
            fg_color=PANEL2,
            border_color="#2c3340",
        )
        self.model_menu.pack(padx=16, pady=2, fill="x")

        ctk.CTkLabel(side, text="Base URL（可改）", text_color=TEXT_MUTED).pack(
            padx=16, pady=(8, 2), anchor="w"
        )
        self.base_entry = ctk.CTkEntry(side, height=30)
        self.base_entry.pack(padx=16, pady=2, fill="x")

        ctk.CTkLabel(side, text="API Key", text_color=TEXT_MUTED).pack(
            padx=16, pady=(8, 2), anchor="w"
        )
        self.api_entry = ctk.CTkEntry(side, placeholder_text="sk-…", show="•", height=30)
        self.api_entry.pack(padx=16, pady=2, fill="x")

        ctk.CTkButton(
            side,
            text="保存 Provider 配置",
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            height=34,
            command=self._save_llm_config,
        ).pack(padx=16, pady=(10, 4), fill="x")

        ctk.CTkLabel(
            side,
            text="Key 仅写入本机 .env\n默认推荐：阶跃 Step Plan",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
        ).pack(padx=16, pady=(4, 8), anchor="w")

        # ── BP Meta ──
        ctk.CTkLabel(
            side,
            text="BP Meta 数据源",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=16, pady=(12, 4), anchor="w")

        self.meta_source_menu = ctk.CTkOptionMenu(
            side,
            values=["auto (有 Token 用 STRATZ)", "opendota", "stratz"],
            fg_color=PANEL2,
            button_color="#2c3340",
            button_hover_color="#3a4252",
            height=30,
            command=self._on_meta_source_changed,
        )
        self.meta_source_menu.pack(padx=16, pady=2, fill="x")

        ctk.CTkLabel(
            side, text="STRATZ Token（用户自备）", text_color=TEXT_MUTED
        ).pack(padx=16, pady=(6, 2), anchor="w")
        self.stratz_entry = ctk.CTkEntry(
            side, placeholder_text="Bearer token from stratz.com/api", show="•", height=30
        )
        self.stratz_entry.pack(padx=16, pady=2, fill="x")

        ctk.CTkLabel(side, text="STRATZ 段位", text_color=TEXT_MUTED).pack(
            padx=16, pady=(6, 2), anchor="w"
        )
        self.stratz_bracket_menu = ctk.CTkOptionMenu(
            side,
            values=[
                "high",
                "mid",
                "low",
                "all",
                "divine_immortal",
                "legend_ancient",
                "crusader_archon",
                "herald_guardian",
            ],
            fg_color=PANEL2,
            button_color="#2c3340",
            button_hover_color="#3a4252",
            height=28,
        )
        self.stratz_bracket_menu.pack(padx=16, pady=2, fill="x")

        self.meta_note = ctk.CTkLabel(
            side,
            text="auto：填了 STRATZ Token 用分路 Meta，否则 OpenDota",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
        )
        self.meta_note.pack(padx=16, pady=(4, 4), anchor="w")

        ctk.CTkButton(
            side,
            text="保存 Meta 配置",
            fg_color=PANEL2,
            hover_color="#2c3340",
            height=32,
            command=self._save_meta_config,
        ).pack(padx=16, pady=(2, 8), fill="x")

        # ── ASR / TTS ──
        ctk.CTkLabel(
            side,
            text="语音 ASR / TTS",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(padx=16, pady=(12, 4), anchor="w")

        ctk.CTkLabel(side, text="ASR 识别", text_color=TEXT_MUTED).pack(
            padx=16, pady=(2, 2), anchor="w"
        )
        self.stt_menu = ctk.CTkOptionMenu(
            side,
            values=self._stt_names,
            command=self._on_stt_changed,
            fg_color=PANEL2,
            button_color="#2c3340",
            button_hover_color="#3a4252",
            height=30,
        )
        self.stt_menu.pack(padx=16, pady=2, fill="x")

        self.stt_model_menu = ctk.CTkComboBox(
            side, values=["-"], height=28, fg_color=PANEL2, border_color="#2c3340"
        )
        self.stt_model_menu.pack(padx=16, pady=2, fill="x")

        ctk.CTkLabel(side, text="TTS 播报", text_color=TEXT_MUTED).pack(
            padx=16, pady=(8, 2), anchor="w"
        )
        self.tts_menu = ctk.CTkOptionMenu(
            side,
            values=self._tts_names,
            command=self._on_tts_changed,
            fg_color=PANEL2,
            button_color="#2c3340",
            button_hover_color="#3a4252",
            height=30,
        )
        self.tts_menu.pack(padx=16, pady=2, fill="x")

        self.tts_model_menu = ctk.CTkComboBox(
            side, values=["-"], height=28, fg_color=PANEL2, border_color="#2c3340"
        )
        self.tts_model_menu.pack(padx=16, pady=2, fill="x")

        self.tts_voice_menu = ctk.CTkComboBox(
            side, values=["-"], height=28, fg_color=PANEL2, border_color="#2c3340"
        )
        self.tts_voice_menu.pack(padx=16, pady=2, fill="x")

        self.voice_note = ctk.CTkLabel(
            side,
            text="Step Plan 可用 stepaudio-2.5-asr / tts",
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
        )
        self.voice_note.pack(padx=16, pady=(4, 4), anchor="w")

        ctk.CTkButton(
            side,
            text="保存语音配置",
            fg_color=PANEL2,
            hover_color="#2c3340",
            height=32,
            command=self._save_voice_config,
        ).pack(padx=16, pady=(4, 8), fill="x")

        ctk.CTkLabel(
            side,
            text=f"v{__version__}",
            text_color="#5c6575",
            font=ctk.CTkFont(size=11),
        ).pack(padx=16, pady=(4, 16), anchor="w")

        # Main chat
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=14, pady=14)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=1)

        chat_frame = ctk.CTkFrame(main, fg_color=PANEL, corner_radius=12)
        chat_frame.grid(row=0, column=0, sticky="nsew")
        chat_frame.grid_rowconfigure(0, weight=1)
        chat_frame.grid_columnconfigure(0, weight=1)

        self.chat = ctk.CTkTextbox(
            chat_frame,
            font=ctk.CTkFont(size=14),
            fg_color=PANEL,
            text_color="#e8ecf1",
            wrap="word",
            activate_scrollbars=True,
        )
        self.chat.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.chat.configure(state="disabled")

        input_row = ctk.CTkFrame(main, fg_color="transparent")
        input_row.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        input_row.grid_columnconfigure(0, weight=1)

        self.input = ctk.CTkEntry(
            input_row,
            placeholder_text="问 DoDoClaw… 例如：现在该出什么？买活值不值？",
            height=42,
            font=ctk.CTkFont(size=14),
        )
        self.input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input.bind("<Return>", lambda _e: self._on_send())

        self.btn_send = ctk.CTkButton(
            input_row,
            text="发送",
            width=88,
            height=42,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._on_send,
        )
        self.btn_send.grid(row=0, column=1, padx=(0, 8))

        self.btn_listen = ctk.CTkButton(
            input_row,
            text="🎤 语音",
            width=88,
            height=42,
            fg_color=PANEL2,
            hover_color="#2c3340",
            command=self._on_listen,
        )
        self.btn_listen.grid(row=0, column=2)

    def _load_settings_into_ui(self) -> None:
        settings = get_settings()
        pid, pname, key, url, model = settings.resolve_llm()
        # ensure name in list
        if pname not in self._provider_names:
            pname = get_provider(DEFAULT_PROVIDER_ID).name
            pid = DEFAULT_PROVIDER_ID
        self.provider_menu.set(pname)
        self._apply_provider_to_widgets(pid, keep_key=False)
        if model:
            self.model_menu.set(model)
        if url:
            self.base_entry.delete(0, tk.END)
            self.base_entry.insert(0, url)
        if key:
            self.api_entry.delete(0, tk.END)
            self.api_entry.insert(0, key)

        stt_id = settings.stt_backend or "mock"
        tts_id = settings.tts_backend or "mock"
        self.stt_menu.set(self._stt_id_to_name.get(stt_id, self._stt_names[0]))
        self.tts_menu.set(self._tts_id_to_name.get(tts_id, self._tts_names[0]))
        self._on_stt_changed(self.stt_menu.get())
        self._on_tts_changed(self.tts_menu.get())
        if settings.stt_model:
            self.stt_model_menu.set(settings.stt_model)
        if settings.tts_model:
            self.tts_model_menu.set(settings.tts_model)
        if settings.tts_voice:
            self.tts_voice_menu.set(settings.tts_voice)

        # Meta
        src = (settings.meta_source or "auto").lower()
        src_label = {
            "auto": "auto (有 Token 用 STRATZ)",
            "opendota": "opendota",
            "stratz": "stratz",
        }.get(src, "auto (有 Token 用 STRATZ)")
        self.meta_source_menu.set(src_label)
        if settings.stratz_api_token:
            self.stratz_entry.delete(0, tk.END)
            self.stratz_entry.insert(0, settings.stratz_api_token)
        br = settings.stratz_bracket or "high"
        try:
            self.stratz_bracket_menu.set(br)
        except Exception:
            self.stratz_bracket_menu.set("high")
        self._on_meta_source_changed(src_label)

    def _apply_provider_to_widgets(self, provider_id: str, keep_key: bool = True) -> None:
        spec = get_provider(provider_id)
        self.provider_note.configure(
            text=spec.note or f"Key 环境变量: {spec.key_env}"
        )
        models = spec.model_choices()
        self.model_menu.configure(values=models)
        self.model_menu.set(spec.default_model)
        self.base_entry.delete(0, tk.END)
        self.base_entry.insert(0, spec.base_url)
        if not keep_key:
            return
        # try fill key from settings for this vendor
        settings = get_settings()
        vendor_keys = {
            "stepfun_plan": settings.stepfun_api_key or settings.llm_api_key,
            "stepfun": settings.stepfun_api_key or settings.llm_api_key,
            "deepseek": settings.deepseek_api_key or settings.llm_api_key,
            "dashscope": settings.dashscope_api_key or settings.llm_api_key,
            "zhipu": settings.zhipu_api_key or settings.llm_api_key,
            "moonshot": settings.moonshot_api_key or settings.llm_api_key,
            "siliconflow": settings.siliconflow_api_key or settings.llm_api_key,
            "volcengine": settings.ark_api_key or settings.llm_api_key,
            "minimax": settings.minimax_api_key or settings.llm_api_key,
            "yi": settings.yi_api_key or settings.llm_api_key,
            "baichuan": settings.baichuan_api_key or settings.llm_api_key,
            "openai": settings.openai_api_key or settings.llm_api_key,
            "xai": settings.xai_api_key or settings.llm_api_key,
            "custom": settings.llm_api_key,
        }
        k = (vendor_keys.get(spec.id) or settings.llm_api_key or "").strip()
        if k:
            self.api_entry.delete(0, tk.END)
            self.api_entry.insert(0, k)

    def _on_provider_changed(self, name: str) -> None:
        pid = provider_id_from_name(name)
        self._apply_provider_to_widgets(pid, keep_key=True)
        self._append_system(f"已选择 Provider: {name}")

    def _meta_source_id(self) -> str:
        raw = self.meta_source_menu.get()
        if raw.startswith("auto"):
            return "auto"
        return raw.strip().lower()

    def _on_meta_source_changed(self, name: str) -> None:
        sid = "auto" if str(name).startswith("auto") else str(name).lower()
        notes = {
            "auto": "有 STRATZ Token → STRATZ（含分路）；否则 OpenDota",
            "opendota": "OpenDota：免 Token，有段位 1–8，无分路聚合",
            "stratz": "STRATZ：需 Token（stratz.com/api），支持段位+分路",
        }
        self.meta_note.configure(text=notes.get(sid, notes["auto"]))

    def _save_meta_config(self) -> None:
        source = self._meta_source_id()
        token = self.stratz_entry.get().strip()
        bracket = self.stratz_bracket_menu.get().strip() or "high"
        pairs = {
            "META_SOURCE": source,
            "STRATZ_BRACKET": bracket,
        }
        if token:
            pairs["STRATZ_API_TOKEN"] = token
        path = save_env_values(pairs)
        if self._service:
            self._service.reload_meta(
                source=source,
                stratz_token=token or None,
                stratz_bracket=bracket,
            )
        src_name = (
            self._service._draft_advisor.source_name
            if self._service and self._service._draft_advisor
            else source
        )
        messagebox.showinfo(
            "已保存",
            f"META_SOURCE={source}\n实际加载: {src_name}\n"
            f"STRATZ_BRACKET={bracket}\n写入: {path}\n\n"
            "Token 获取: https://stratz.com/api\n"
            "人多后请各自使用自己的 Token。",
        )
        self._append_system(f"Meta 配置已保存 → {src_name} (source={source})")

    def _on_stt_changed(self, name: str) -> None:
        bid = self._stt_name_to_id.get(name, "mock")
        spec = get_stt_backend(bid)
        models = list(spec.models) if spec.models else ([spec.default_model] if spec.default_model else ["-"])
        self.stt_model_menu.configure(values=models)
        self.stt_model_menu.set(spec.default_model or models[0])
        self.voice_note.configure(text=spec.note or "")

    def _on_tts_changed(self, name: str) -> None:
        bid = self._tts_name_to_id.get(name, "mock")
        spec = get_tts_backend(bid)
        models = list(spec.models) if spec.models else ([spec.default_model] if spec.default_model else ["-"])
        self.tts_model_menu.configure(values=models)
        self.tts_model_menu.set(spec.default_model or models[0])
        voices = list(spec.voices) if spec.voices else (["-"])
        self.tts_voice_menu.configure(values=voices)
        self.tts_voice_menu.set(voices[0])
        note = spec.note or ""
        if bid.startswith("stepfun"):
            note = (note + " · 与 LLM 共用 Step API Key").strip(" ·")
        self.voice_note.configure(text=note)

    def _current_provider_id(self) -> str:
        return provider_id_from_name(self.provider_menu.get())

    def _current_stt_id(self) -> str:
        return self._stt_name_to_id.get(self.stt_menu.get(), "mock")

    def _current_tts_id(self) -> str:
        return self._tts_name_to_id.get(self.tts_menu.get(), "mock")

    # ── UI helpers ──────────────────────────────────────────
    def _append_chat(self, role: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat.configure(state="normal")
        if role == "user":
            self.chat.insert("end", f"[{ts}] 你\n{text}\n\n")
        elif role == "assistant":
            self.chat.insert("end", f"[{ts}] DoDoClaw\n{text}\n\n")
        else:
            self.chat.insert("end", f"[{ts}] 系统  ·  {text}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_system(self, text: str) -> None:
        self._append_chat("system", text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.btn_send.configure(state=state)
        self.btn_listen.configure(state=state)

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    level, msg = payload
                    if level in {"info", "warning", "error"}:
                        self._append_system(msg)
                elif kind == "assistant":
                    self._append_chat("assistant", payload)
                    self._set_busy(False)
                elif kind == "user":
                    self._append_chat("user", payload)
                elif kind == "error":
                    self._append_system(f"错误: {payload}")
                    self._set_busy(False)
                elif kind == "gsi":
                    self.gsi_label.configure(text=payload)
                elif kind == "reminder":
                    self._append_system(f"⏰ {payload}")
        except queue.Empty:
            pass
        self.after(120, self._poll_ui_queue)

    def _refresh_status_loop(self) -> None:
        if self._service and self._service.running:
            snap = self._service.snapshot()
            if self._service.gsi_update_count > 0:
                hero = (
                    snap.hero_name.replace("npc_dota_hero_", "")
                    if snap.hero_name
                    else "—"
                )
                text = (
                    f"GSI: 已连接 · {snap.clock_mmss}\n"
                    f"{hero} Lv{snap.hero_level} · 金 {snap.gold}\n"
                    f"包数 {self._service.gsi_update_count}"
                )
            else:
                text = "GSI: 服务已开，等待 Dota 推送…\n（需安装配置并重启游戏）"
            self.gsi_label.configure(text=text)
            self.status_dot.configure(text="●  服务运行中", text_color="#3ecf8e")
            self.btn_start.configure(text="停止服务")
        else:
            self.status_dot.configure(text="●  服务未启动", text_color="#e5a84b")
            self.btn_start.configure(text="启动服务")
        self.after(1000, self._refresh_status_loop)

    def _apply_llm_to_service(self) -> None:
        pid = self._current_provider_id()
        key = self.api_entry.get().strip()
        base = self.base_entry.get().strip()
        model = self.model_menu.get().strip()
        if self._service:
            self._service.reload_llm(
                provider_id=pid,
                api_key=key or None,
                base_url=base or None,
                model=model or None,
            )
            self._apply_voice_to_service()

    def _apply_voice_to_service(self) -> None:
        if not self._service:
            return
        self._service.reload_voice(
            stt_backend=self._current_stt_id(),
            tts_backend=self._current_tts_id(),
            stt_model=self.stt_model_menu.get().strip() or None,
            tts_model=self.tts_model_menu.get().strip() or None,
            tts_voice=self.tts_voice_menu.get().strip() or None,
        )

    # ── actions ─────────────────────────────────────────────
    def _ensure_service(self) -> DoDoClawService:
        if self._service is None:
            self._service = DoDoClawService(
                on_log=lambda lvl, msg: self._ui_queue.put(("log", (lvl, msg))),
                on_reminder=lambda ev: self._ui_queue.put(("reminder", ev.message)),
                on_gsi=lambda snap: self._ui_queue.put(
                    (
                        "gsi",
                        f"GSI: {snap.clock_mmss} · "
                        f"{(snap.hero_name or '—').replace('npc_dota_hero_', '')}",
                    )
                ),
            )
            self._apply_llm_to_service()
        return self._service

    def _toggle_service(self) -> None:
        svc = self._ensure_service()
        if svc.running:
            svc.stop()
            self._append_system("服务已停止")
        else:
            self._apply_llm_to_service()
            svc.start()
            self._append_system(
                f"服务已启动 · {svc.provider_name} / {svc.coach.model}"
            )

    def _install_gsi(self) -> None:
        ok, msg, _dest = install_gsi_cfg()
        if ok:
            messagebox.showinfo("GSI 安装成功", msg)
            self._append_system(msg.replace("\n", " "))
        else:
            messagebox.showwarning("GSI 安装失败", msg)
            self._append_system(msg)

    def _save_llm_config(self) -> None:
        pid = self._current_provider_id()
        spec = get_provider(pid)
        key = self.api_entry.get().strip()
        base = self.base_entry.get().strip()
        model = self.model_menu.get().strip()
        if not key:
            messagebox.showwarning("提示", "请先输入 API Key")
            return

        pairs = {
            "LLM_PROVIDER": pid,
            "LLM_API_KEY": key,
            "LLM_BASE_URL": base or spec.base_url,
            "LLM_MODEL": model or spec.default_model,
        }
        # Also write vendor-specific key for convenience
        if spec.key_env and spec.key_env != "LLM_API_KEY":
            pairs[spec.key_env] = key

        path = save_env_values(pairs)
        self._apply_llm_to_service()
        messagebox.showinfo(
            "已保存",
            f"Provider: {spec.name}\nModel: {pairs['LLM_MODEL']}\n写入: {path}",
        )
        self._append_system(
            f"已保存 LLM 配置: {spec.name} / {pairs['LLM_MODEL']}"
        )

    def _save_voice_config(self) -> None:
        stt_id = self._current_stt_id()
        tts_id = self._current_tts_id()
        stt_model = self.stt_model_menu.get().strip()
        tts_model = self.tts_model_menu.get().strip()
        tts_voice = self.tts_voice_menu.get().strip()
        pairs = {
            "STT_BACKEND": stt_id,
            "TTS_BACKEND": tts_id,
            "STT_MODEL": stt_model if stt_model not in {"", "-"} else "",
            "TTS_MODEL": tts_model if tts_model not in {"", "-"} else "",
            "TTS_VOICE": tts_voice if tts_voice not in {"", "-"} else "",
        }
        path = save_env_values({k: v for k, v in pairs.items() if v != "" or k.endswith("BACKEND")})
        # always write backends even if empty models
        save_env_values(pairs)
        if self._service:
            self._apply_voice_to_service()
        messagebox.showinfo(
            "已保存",
            f"ASR: {stt_id} ({stt_model or '-'})\n"
            f"TTS: {tts_id} ({tts_model or '-'} / {tts_voice or '-'})\n"
            f"写入: {path}",
        )
        self._append_system(f"已保存语音配置 STT={stt_id} TTS={tts_id}")

    def _show_status(self) -> None:
        svc = self._ensure_service()
        self._append_system(svc.status_text())

    def _show_draft(self) -> None:
        svc = self._ensure_service()
        self._append_system("正在拉取 OpenDota Meta / BP 数据…")
        self._set_busy(True)

        def work() -> None:
            try:
                text = svc.draft_advice(speak=False)
                self._ui_queue.put(("assistant", text))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=work, name="draft", daemon=True).start()

    def _on_send(self) -> None:
        text = self.input.get().strip()
        if not text or self._busy:
            return
        self.input.delete(0, tk.END)
        self._ask_async(text)

    def _on_listen(self) -> None:
        if self._busy:
            return
        svc = self._ensure_service()
        if not svc.running:
            self._apply_llm_to_service()
            svc.start()
        self._set_busy(True)
        self._append_system("正在听…（mock 模式会弹出输入；whisper 需额外安装）")

        def work() -> None:
            try:
                text = svc.listen_once()
                if not text:
                    self._ui_queue.put(("error", "未识别到内容"))
                    return
                self._ui_queue.put(("user", text))
                answer = svc.ask(text, speak=True)
                self._ui_queue.put(("assistant", answer))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=work, name="listen", daemon=True).start()

    def _ask_async(self, text: str) -> None:
        svc = self._ensure_service()
        if not svc.running:
            self._apply_llm_to_service()
            svc.start()
        else:
            self._apply_llm_to_service()

        self._append_chat("user", text)
        self._set_busy(True)

        def work() -> None:
            try:
                answer = svc.ask(text, speak=True)
                self._ui_queue.put(("assistant", answer))
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=work, name="ask", daemon=True).start()

    def _on_close(self) -> None:
        try:
            if self._service and self._service.running:
                self._service.stop()
        finally:
            self.destroy()


def run_gui() -> int:
    app = DoDoClawDesktop()
    app.mainloop()
    return 0
