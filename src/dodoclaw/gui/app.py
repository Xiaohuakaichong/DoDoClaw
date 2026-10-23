"""DoDoClaw desktop UI — restrained dark layout (chat-first, collapsible settings)."""

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
from dodoclaw.config import get_settings, save_coach_choice, save_env_values
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

# Design tokens — dark, quiet, high contrast where it matters
BG = "#0b0c0f"
SURFACE = "#12141a"
SURFACE_2 = "#1a1d26"
BORDER = "#2a2e38"
TEXT = "#eceef2"
MUTED = "#8b929e"
ACCENT = "#c23c2a"
ACCENT_HOVER = "#a83426"
OK = "#3dcb8c"
WARN = "#e0a84a"
SIDEBAR_W = 320


class DoDoClawDesktop(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"DoDoClaw  ·  v{__version__}")
        self.geometry("1080x720")
        self.minsize(880, 560)
        self.configure(fg_color=BG)

        self._ui_queue: queue.Queue = queue.Queue()
        self._service: DoDoClawService | None = None
        self._busy = False
        self._settings_open = False
        self._bp_window = None

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
        self.after(100, self._poll_ui_queue)
        self.after(1000, self._refresh_status_loop)

        self._append_system(
            "DoDoClaw 已就绪。文字提问只回文字；点「语音」才会语音播报。"
            " 首次使用点右上角「设置」配置 Provider 与 API Key。"
        )

    # ── layout ──────────────────────────────────────────────
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_topbar()
        self._build_body()
        self._build_composer()

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=SURFACE, height=56, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(2, weight=1)

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w", padx=(16, 8), pady=10)
        ctk.CTkLabel(
            brand,
            text="DoDoClaw",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")
        ctk.CTkLabel(
            brand,
            text="  Dota 2",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        ).pack(side="left")

        self.status_pill = ctk.CTkLabel(
            bar,
            text="● 未启动",
            font=ctk.CTkFont(size=12),
            text_color=WARN,
            fg_color=SURFACE_2,
            corner_radius=8,
            padx=10,
            pady=4,
        )
        self.status_pill.grid(row=0, column=1, sticky="w", padx=6)

        self.gsi_chip = ctk.CTkLabel(
            bar,
            text="GSI · 等待",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
            fg_color=SURFACE_2,
            corner_radius=8,
            padx=10,
            pady=4,
        )
        self.gsi_chip.grid(row=0, column=2, sticky="w", padx=4)

        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.grid(row=0, column=3, sticky="e", padx=12, pady=10)

        self.btn_start = ctk.CTkButton(
            actions,
            text="启动",
            width=72,
            height=32,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._toggle_service,
        )
        self.btn_start.pack(side="left", padx=3)

        self._ghost_btn(actions, "GSI", self._install_gsi, w=56).pack(side="left", padx=3)
        self._ghost_btn(actions, "局势", self._show_status, w=56).pack(side="left", padx=3)
        self._ghost_btn(actions, "BP", self._show_draft, w=48).pack(side="left", padx=3)

        self.btn_settings = ctk.CTkButton(
            actions,
            text="设置",
            width=64,
            height=32,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            font=ctk.CTkFont(size=13),
            command=self._toggle_settings,
        )
        self.btn_settings.pack(side="left", padx=(8, 0))

    def _ghost_btn(self, parent, text, cmd, w=64):
        return ctk.CTkButton(
            parent,
            text=text,
            width=w,
            height=32,
            fg_color="transparent",
            hover_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=ctk.CTkFont(size=12),
            command=cmd,
        )

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._body = body

        # Settings drawer (hidden by default)
        self.settings_frame = ctk.CTkFrame(
            body, width=SIDEBAR_W, fg_color=SURFACE, corner_radius=0
        )
        self.settings_frame.grid_propagate(False)
        self._build_settings_content(self.settings_frame)
        # not gridded until open

        # Chat panel
        chat_wrap = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        chat_wrap.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        chat_wrap.grid_rowconfigure(0, weight=1)
        chat_wrap.grid_columnconfigure(0, weight=1)
        self._chat_wrap = chat_wrap

        self.chat = ctk.CTkTextbox(
            chat_wrap,
            font=ctk.CTkFont(size=14),
            fg_color=BG,
            text_color=TEXT,
            wrap="word",
            activate_scrollbars=True,
            border_width=0,
            corner_radius=0,
        )
        self.chat.grid(row=0, column=0, sticky="nsew", padx=20, pady=(12, 4))
        self.chat.configure(state="disabled")

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=MUTED,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 4))

    def _build_settings_content(self, root: ctk.CTkFrame) -> None:
        head = ctk.CTkFrame(root, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(14, 4))
        ctk.CTkLabel(
            head,
            text="设置",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")
        ctk.CTkButton(
            head,
            text="收起",
            width=56,
            height=28,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            font=ctk.CTkFont(size=12),
            command=self._toggle_settings,
        ).pack(side="right")

        tabs = ctk.CTkTabview(
            root,
            fg_color=SURFACE,
            segmented_button_fg_color=SURFACE_2,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            segmented_button_unselected_color=SURFACE_2,
            segmented_button_unselected_hover_color=BORDER,
            text_color=TEXT,
            height=520,
        )
        tabs.pack(fill="both", expand=True, padx=8, pady=(4, 12))
        tab_llm = tabs.add("模型")
        tab_voice = tabs.add("语音")
        tab_meta = tabs.add("Meta")

        # ── LLM tab ──
        scroll_llm = ctk.CTkScrollableFrame(tab_llm, fg_color="transparent")
        scroll_llm.pack(fill="both", expand=True)

        self._section_label(scroll_llm, "服务商")
        self.provider_menu = ctk.CTkOptionMenu(
            scroll_llm,
            values=self._provider_names,
            command=self._on_provider_changed,
            fg_color=SURFACE_2,
            button_color=BORDER,
            button_hover_color="#353a46",
            height=34,
            dynamic_resizing=False,
        )
        self.provider_menu.pack(fill="x", padx=14, pady=2)

        self.provider_note = ctk.CTkLabel(
            scroll_llm,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
            anchor="w",
        )
        self.provider_note.pack(fill="x", padx=14, pady=(4, 2))

        self._section_label(scroll_llm, "模型")
        self.model_menu = ctk.CTkComboBox(
            scroll_llm,
            values=["step-3.7-flash"],
            height=34,
            fg_color=SURFACE_2,
            border_color=BORDER,
        )
        self.model_menu.pack(fill="x", padx=14, pady=2)

        self._section_label(scroll_llm, "Base URL（可覆盖）")
        self.base_entry = ctk.CTkEntry(
            scroll_llm,
            height=34,
            fg_color=SURFACE_2,
            border_color=BORDER,
            placeholder_text="https://…",
        )
        self.base_entry.pack(fill="x", padx=14, pady=2)
        ctk.CTkButton(
            scroll_llm,
            text="恢复默认 URL",
            height=28,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            font=ctk.CTkFont(size=12),
            command=self._reset_base_url,
        ).pack(fill="x", padx=14, pady=(4, 2))

        self._section_label(scroll_llm, "API Key")
        self.api_entry = ctk.CTkEntry(
            scroll_llm,
            height=34,
            fg_color=SURFACE_2,
            border_color=BORDER,
            placeholder_text="粘贴 API Key",
            show="•",
        )
        self.api_entry.pack(fill="x", padx=14, pady=2)

        ctk.CTkButton(
            scroll_llm,
            text="保存模型配置",
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_llm_config,
        ).pack(fill="x", padx=14, pady=(16, 8))

        ctk.CTkLabel(
            scroll_llm,
            text="Key 仅保存在本机 · 不会上传",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(padx=14, pady=(0, 12), anchor="w")

        # ── Voice tab ──
        scroll_v = ctk.CTkScrollableFrame(tab_voice, fg_color="transparent")
        scroll_v.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll_v,
            text="文字发送 → 只显示文字\n语音发送 → 识别后播报回复",
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 4))

        self._section_label(scroll_v, "ASR 识别")
        self.stt_menu = ctk.CTkOptionMenu(
            scroll_v,
            values=self._stt_names,
            command=self._on_stt_changed,
            fg_color=SURFACE_2,
            button_color=BORDER,
            button_hover_color="#353a46",
            height=34,
        )
        self.stt_menu.pack(fill="x", padx=14, pady=2)
        self.stt_model_menu = ctk.CTkComboBox(
            scroll_v, values=["-"], height=32, fg_color=SURFACE_2, border_color=BORDER
        )
        self.stt_model_menu.pack(fill="x", padx=14, pady=2)

        self._section_label(scroll_v, "TTS 播报（仅语音提问时）")
        self.tts_menu = ctk.CTkOptionMenu(
            scroll_v,
            values=self._tts_names,
            command=self._on_tts_changed,
            fg_color=SURFACE_2,
            button_color=BORDER,
            button_hover_color="#353a46",
            height=34,
        )
        self.tts_menu.pack(fill="x", padx=14, pady=2)
        self.tts_model_menu = ctk.CTkComboBox(
            scroll_v, values=["-"], height=32, fg_color=SURFACE_2, border_color=BORDER
        )
        self.tts_model_menu.pack(fill="x", padx=14, pady=2)
        self.tts_voice_menu = ctk.CTkComboBox(
            scroll_v, values=["-"], height=32, fg_color=SURFACE_2, border_color=BORDER
        )
        self.tts_voice_menu.pack(fill="x", padx=14, pady=2)

        self.voice_note = ctk.CTkLabel(
            scroll_v,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
            anchor="w",
        )
        self.voice_note.pack(fill="x", padx=14, pady=6)

        ctk.CTkButton(
            scroll_v,
            text="保存语音配置",
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._save_voice_config,
        ).pack(fill="x", padx=14, pady=(8, 12))

        # ── Meta tab ──
        scroll_m = ctk.CTkScrollableFrame(tab_meta, fg_color="transparent")
        scroll_m.pack(fill="both", expand=True)

        self._section_label(scroll_m, "数据源")
        self.meta_source_menu = ctk.CTkOptionMenu(
            scroll_m,
            values=["auto (有 Token 用 STRATZ)", "opendota", "stratz"],
            command=self._on_meta_source_changed,
            fg_color=SURFACE_2,
            button_color=BORDER,
            button_hover_color="#353a46",
            height=34,
        )
        self.meta_source_menu.pack(fill="x", padx=14, pady=2)

        self._section_label(scroll_m, "STRATZ Token")
        self.stratz_entry = ctk.CTkEntry(
            scroll_m,
            height=34,
            fg_color=SURFACE_2,
            border_color=BORDER,
            placeholder_text="stratz.com/api",
            show="•",
        )
        self.stratz_entry.pack(fill="x", padx=14, pady=2)

        self._section_label(scroll_m, "STRATZ 段位")
        self.stratz_bracket_menu = ctk.CTkOptionMenu(
            scroll_m,
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
            fg_color=SURFACE_2,
            button_color=BORDER,
            button_hover_color="#353a46",
            height=32,
        )
        self.stratz_bracket_menu.pack(fill="x", padx=14, pady=2)

        self.meta_note = ctk.CTkLabel(
            scroll_m,
            text="",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
            justify="left",
            wraplength=260,
            anchor="w",
        )
        self.meta_note.pack(fill="x", padx=14, pady=6)

        ctk.CTkButton(
            scroll_m,
            text="保存 Meta 配置",
            height=36,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._save_meta_config,
        ).pack(fill="x", padx=14, pady=(8, 12))

        ctk.CTkLabel(
            scroll_m,
            text=f"v{__version__}  ·  Data by OpenDota / STRATZ",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(padx=14, pady=(4, 12), anchor="w")

    def _build_composer(self) -> None:
        foot = ctk.CTkFrame(self, fg_color=SURFACE, height=72, corner_radius=0)
        foot.grid(row=2, column=0, sticky="ew")
        foot.grid_propagate(False)
        foot.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(foot, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=12)
        inner.grid_columnconfigure(0, weight=1)

        self.input = ctk.CTkEntry(
            inner,
            height=44,
            font=ctk.CTkFont(size=14),
            fg_color=SURFACE_2,
            border_color=BORDER,
            border_width=1,
            placeholder_text="输入问题，Enter 发送（仅文字回复）…",
            text_color=TEXT,
        )
        self.input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.input.bind("<Return>", lambda _e: self._on_send())

        self.btn_send = ctk.CTkButton(
            inner,
            text="发送",
            width=88,
            height=44,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_send,
        )
        self.btn_send.grid(row=0, column=1, padx=(0, 6))

        self.btn_listen = ctk.CTkButton(
            inner,
            text="语音",
            width=80,
            height=44,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            font=ctk.CTkFont(size=14),
            command=self._on_listen,
        )
        self.btn_listen.grid(row=0, column=2)

    def _toggle_settings(self) -> None:
        if self._settings_open:
            self.settings_frame.grid_forget()
            self._settings_open = False
            self.btn_settings.configure(fg_color=SURFACE_2, text="设置")
        else:
            self.settings_frame.grid(row=0, column=0, sticky="nsew")
            self.settings_frame.configure(width=SIDEBAR_W)
            self._settings_open = True
            self.btn_settings.configure(fg_color=ACCENT, text="收起")

    # ── settings load / provider helpers ────────────────────
    def _load_settings_into_ui(self) -> None:
        settings = get_settings()
        pid, pname, key, url, model = settings.resolve_llm()
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
        try:
            self.stratz_bracket_menu.set(settings.stratz_bracket or "high")
        except Exception:
            self.stratz_bracket_menu.set("high")
        self._on_meta_source_changed(src_label)

    def _apply_provider_to_widgets(self, provider_id: str, keep_key: bool = True) -> None:
        spec = get_provider(provider_id)
        note = spec.note or f"Key: {spec.key_env}"
        if spec.docs_url:
            note = f"{note}\n{spec.docs_url}"
        self.provider_note.configure(text=note)
        models = spec.model_choices()
        self.model_menu.configure(values=models)
        self.model_menu.set(spec.default_model)
        self.base_entry.delete(0, tk.END)
        self.base_entry.insert(0, spec.base_url)
        if not keep_key:
            return
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
        self._apply_provider_to_widgets(provider_id_from_name(name), keep_key=True)

    def _reset_base_url(self) -> None:
        spec = get_provider(self._current_provider_id())
        self.base_entry.delete(0, tk.END)
        self.base_entry.insert(0, spec.base_url)

    def _meta_source_id(self) -> str:
        raw = self.meta_source_menu.get()
        return "auto" if raw.startswith("auto") else raw.strip().lower()

    def _on_meta_source_changed(self, name: str) -> None:
        sid = "auto" if str(name).startswith("auto") else str(name).lower()
        notes = {
            "auto": "有 STRATZ Token → 分路 Meta；否则 OpenDota",
            "opendota": "OpenDota：免 Token，段位 1–8",
            "stratz": "STRATZ：需 Token，支持段位 + 分路",
        }
        self.meta_note.configure(text=notes.get(sid, notes["auto"]))

    def _on_stt_changed(self, name: str) -> None:
        bid = self._stt_name_to_id.get(name, "mock")
        spec = get_stt_backend(bid)
        models = list(spec.models) if spec.models else (
            [spec.default_model] if spec.default_model else ["-"]
        )
        self.stt_model_menu.configure(values=models)
        self.stt_model_menu.set(spec.default_model or models[0])
        self.voice_note.configure(text=spec.note or "")

    def _on_tts_changed(self, name: str) -> None:
        bid = self._tts_name_to_id.get(name, "mock")
        spec = get_tts_backend(bid)
        models = list(spec.models) if spec.models else (
            [spec.default_model] if spec.default_model else ["-"]
        )
        self.tts_model_menu.configure(values=models)
        self.tts_model_menu.set(spec.default_model or models[0])
        voices = list(spec.voices) if spec.voices else ["-"]
        self.tts_voice_menu.configure(values=voices)
        self.tts_voice_menu.set(voices[0])
        note = spec.note or ""
        if bid.startswith("stepfun"):
            note = (note + " · 与 LLM 共用 Step Key").strip(" ·")
        self.voice_note.configure(text=note)

    def _current_provider_id(self) -> str:
        return provider_id_from_name(self.provider_menu.get())

    def _current_stt_id(self) -> str:
        return self._stt_name_to_id.get(self.stt_menu.get(), "mock")

    def _current_tts_id(self) -> str:
        return self._tts_name_to_id.get(self.tts_menu.get(), "mock")

    # ── chat / busy ─────────────────────────────────────────
    def _append_chat(self, role: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        self.chat.configure(state="normal")
        if role == "user":
            self.chat.insert("end", f"{ts}  你\n{text}\n\n")
        elif role == "assistant":
            self.chat.insert("end", f"{ts}  DoDoClaw\n{text}\n\n")
        else:
            self.chat.insert("end", f"{ts}  ·  {text}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_system(self, text: str) -> None:
        self._append_chat("system", text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        try:
            self.btn_send.configure(state=state)
            self.btn_listen.configure(state=state)
        except Exception:
            pass
        if busy:
            self.after(90_000, self._busy_watchdog)

    def _busy_watchdog(self) -> None:
        if self._busy:
            self._set_busy(False)
            self._append_system("等待超时。可重试；若语音卡住，将 TTS 改为 mock。")

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self._ui_queue.get_nowait()
                if kind == "log":
                    level, msg = payload
                    if level in {"info", "warning", "error"}:
                        # Skip noise + Q/A that already appear as chat bubbles
                        m = (msg or "").strip()
                        if m.startswith("你:") or m.startswith("DoDoClaw:"):
                            continue
                        if any(
                            x in m
                            for x in (
                                "LLM 已切换",
                                "语音栈已更新",
                                "LLM sync",
                                "BP Meta 已加载",
                                "服务已启动",
                                "服务已停止",
                            )
                        ):
                            continue
                        self._append_system(msg)
                elif kind == "assistant":
                    self._append_chat("assistant", payload)
                    self._set_busy(False)
                elif kind == "user":
                    self._append_chat("user", payload)
                elif kind == "status":
                    self._append_system(str(payload))
                elif kind == "error":
                    self._append_system(f"错误 · {payload}")
                    self._set_busy(False)
                elif kind == "gsi":
                    self.gsi_chip.configure(text=str(payload)[:48], text_color=OK)
                elif kind == "reminder":
                    self._append_system(f"提醒 · {payload}")
        except queue.Empty:
            pass
        self.after(100, self._poll_ui_queue)

    def _refresh_status_loop(self) -> None:
        if self._service and self._service.running:
            snap = self._service.snapshot()
            self.status_pill.configure(text="● 运行中", text_color=OK)
            self.btn_start.configure(text="停止")
            if self._service.gsi_update_count > 0:
                hero = (
                    snap.hero_name.replace("npc_dota_hero_", "")
                    if snap.hero_name
                    else "—"
                )
                self.gsi_chip.configure(
                    text=f"GSI · {snap.clock_mmss} · {hero}",
                    text_color=OK,
                )
            else:
                self.gsi_chip.configure(text="GSI · 等待对局", text_color=WARN)
        else:
            self.status_pill.configure(text="● 未启动", text_color=WARN)
            self.btn_start.configure(text="启动")
        self.after(1000, self._refresh_status_loop)

    def _apply_llm_to_service(self, *, rebuild_voice: bool = False) -> None:
        pid = self._current_provider_id()
        key = self.api_entry.get().strip()
        base = self.base_entry.get().strip()
        model = self.model_menu.get().strip()
        if not self._service:
            return
        if rebuild_voice:
            self._service.reload_llm(
                provider_id=pid,
                api_key=key or None,
                base_url=base or None,
                model=model or None,
            )
            self._apply_voice_to_service()
        else:
            self._service.sync_llm_from_ui(
                provider_id=pid, api_key=key, base_url=base, model=model
            )

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
                        f"GSI · {snap.clock_mmss} · "
                        f"{(snap.hero_name or '—').replace('npc_dota_hero_', '')}",
                    )
                ),
            )
            self._apply_llm_to_service(rebuild_voice=True)
        return self._service

    def _toggle_service(self) -> None:
        svc = self._ensure_service()
        if svc.running:
            svc.stop()
            self._append_system("服务已停止")
        else:
            self._apply_llm_to_service(rebuild_voice=True)
            svc.start()
            key_ok = bool((svc.coach.api_key or "").strip())
            self._append_system(
                f"服务已启动 · {svc.provider_name} / {svc.coach.model}"
                + ("" if key_ok else " · 未设置 Key")
            )

    def _install_gsi(self) -> None:
        ok, msg, _dest = install_gsi_cfg()
        if ok:
            messagebox.showinfo("GSI", msg)
            self._append_system("GSI 配置已安装，请完全重启 Dota 2")
        else:
            messagebox.showwarning("GSI", msg)
            self._append_system(msg)

    def _save_llm_config(self) -> None:
        pid = self._current_provider_id()
        spec = get_provider(pid)
        key = self.api_entry.get().strip()
        base = self.base_entry.get().strip() or spec.base_url
        model = self.model_menu.get().strip() or spec.default_model
        if not key:
            messagebox.showwarning("提示", "请先输入 API Key")
            return
        self.base_entry.delete(0, tk.END)
        self.base_entry.insert(0, base)
        # PRD D9: .env only holds keys; provider / model go to config/settings.yaml
        pairs = {"LLM_API_KEY": key}
        if spec.key_env and spec.key_env != "LLM_API_KEY":
            pairs[spec.key_env] = key
        save_env_values(pairs)
        path = save_coach_choice(pid, model, "" if base.rstrip("/") == spec.base_url.rstrip("/") else base)
        if self._service:
            self._apply_llm_to_service(rebuild_voice=False)
        self._append_system(f"已保存 · {spec.name} / {model}")
        messagebox.showinfo("已保存", f"{spec.name}\n{model}\n{base}\n\n{path}")

    def _save_voice_config(self) -> None:
        pairs = {
            "STT_BACKEND": self._current_stt_id(),
            "TTS_BACKEND": self._current_tts_id(),
            "STT_MODEL": self.stt_model_menu.get().strip(),
            "TTS_MODEL": self.tts_model_menu.get().strip(),
            "TTS_VOICE": self.tts_voice_menu.get().strip(),
        }
        pairs = {k: v for k, v in pairs.items() if v and v != "-"}
        pairs["STT_BACKEND"] = self._current_stt_id()
        pairs["TTS_BACKEND"] = self._current_tts_id()
        path = save_env_values(pairs)
        if self._service:
            self._apply_voice_to_service()
        self._append_system(
            f"语音已保存 · STT={pairs['STT_BACKEND']} TTS={pairs['TTS_BACKEND']}"
        )
        messagebox.showinfo("已保存", f"写入 {path}")

    def _save_meta_config(self) -> None:
        source = self._meta_source_id()
        token = self.stratz_entry.get().strip()
        bracket = self.stratz_bracket_menu.get().strip() or "high"
        pairs = {"META_SOURCE": source, "STRATZ_BRACKET": bracket}
        if token:
            pairs["STRATZ_API_TOKEN"] = token
        path = save_env_values(pairs)
        if self._service:
            self._service.reload_meta(
                source=source, stratz_token=token or None, stratz_bracket=bracket
            )
        name = (
            self._service._draft_advisor.source_name
            if self._service and self._service._draft_advisor
            else source
        )
        self._append_system(f"Meta · {name}")
        messagebox.showinfo("已保存", f"{name}\n{path}")

    def _show_status(self) -> None:
        self._append_system(self._ensure_service().status_text())

    def _show_draft(self) -> None:
        """Open dedicated BP board window (not chat dump)."""
        svc = self._ensure_service()
        if not getattr(svc, "_draft_advisor", None):
            self._append_system("Meta 未启用 · 请在设置 → Meta 中配置数据源")
            # still open window to show empty state / refresh later
        try:
            from dodoclaw.gui.bp_window import BPWindow

            if self._bp_window is not None and self._bp_window.winfo_exists():
                self._bp_window.focus()
                self._bp_window.refresh()
                return

            def ask_from_bp(prompt: str) -> None:
                self._ask_async(prompt, with_voice=False)

            self._bp_window = BPWindow(self, svc, on_ask_coach=ask_from_bp)
            self._bp_window.protocol(
                "WM_DELETE_WINDOW",
                lambda: (self._bp_window.destroy(), setattr(self, "_bp_window", None)),
            )
            self._append_system("已打开 BP 选人面板")
        except Exception as exc:
            logger.exception("open BP window failed")
            self._append_system(f"打开 BP 面板失败: {exc}")
            # fallback text
            self._set_busy(True)

            def work() -> None:
                try:
                    text = svc.draft_advice(speak=False)
                    self._ui_queue.put(("assistant", text))
                except Exception as e:
                    self._ui_queue.put(("error", str(e)))

            threading.Thread(target=work, name="draft", daemon=True).start()

    def _on_send(self) -> None:
        """Text channel: reply with text only (no TTS)."""
        text = self.input.get().strip()
        if not text:
            return
        if self._busy:
            self._append_system("仍在处理上一条，请稍候")
            return
        self.input.delete(0, tk.END)
        self._ask_async(text, with_voice=False)

    def _on_listen(self) -> None:
        """Voice channel: STT → LLM → text + TTS."""
        if self._busy:
            self._append_system("仍在处理中")
            return
        svc = self._ensure_service()
        self._apply_llm_to_service(rebuild_voice=not svc.running)
        if not svc.running:
            try:
                svc.start()
            except Exception as exc:
                self._append_system(f"启动提示: {exc}")
        self._set_busy(True)
        self._append_system("正在听…")

        def work() -> None:
            try:
                text = svc.listen_once()
                if not text:
                    self._ui_queue.put(("error", "未识别到内容"))
                    return
                self._ui_queue.put(("user", text))
                self._ui_queue.put(("status", "识别完成，思考中…"))
                answer = svc.ask(text, speak=False)
                self._ui_queue.put(("assistant", answer or "（空回复）"))
                if answer:
                    threading.Thread(
                        target=lambda: self._speak_safe(svc, answer),
                        name="tts",
                        daemon=True,
                    ).start()
            except Exception as exc:
                self._ui_queue.put(("error", str(exc)))

        threading.Thread(target=work, name="listen", daemon=True).start()

    def _speak_safe(self, svc: DoDoClawService, text: str) -> None:
        try:
            svc.tts.speak(text)
        except Exception as exc:
            self._ui_queue.put(("log", ("warning", f"TTS 失败: {exc}")))

    def _ask_async(self, text: str, *, with_voice: bool) -> None:
        svc = self._ensure_service()
        self._apply_llm_to_service(rebuild_voice=False)
        if not svc.running:
            try:
                svc.start()
            except Exception as exc:
                self._append_system(f"GSI 可选: {exc}")

        if not (svc.coach.api_key or "").strip():
            self._append_system("未设置 API Key · 打开「设置」保存后可正常对话")

        self._append_chat("user", text)
        self._set_busy(True)
        self._append_system("思考中…" + ("（将播报）" if with_voice else ""))

        def work() -> None:
            try:
                answer = svc.ask(text, speak=False)
                if not answer:
                    answer = "（空回复，请检查模型 / 额度）"
                self._ui_queue.put(("assistant", answer))
                if with_voice and answer:
                    threading.Thread(
                        target=lambda: self._speak_safe(svc, answer),
                        name="tts",
                        daemon=True,
                    ).start()
            except Exception as exc:
                logger.exception("ask failed")
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
