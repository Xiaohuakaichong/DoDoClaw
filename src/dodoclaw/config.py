from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from dodoclaw.paths import app_dir, config_dir, ensure_runtime_dirs, ensure_user_config_seeded
from dodoclaw.providers import (
    DEFAULT_PROVIDER_ID,
    get_provider,
    resolve_llm_runtime,
)

logger = logging.getLogger(__name__)

# PRD D9: provider / model / endpoint come only from config/settings.yaml (then the
# code default). These .env variables are read only to log that they are ignored.
IGNORED_ENV = ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "XAI_MODEL", "XAI_BASE_URL")
_ignored_logged = False


def _env_file() -> str:
    return str(app_dir() / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Unified LLM settings. Only the key is used; provider / base URL / model in
    # .env are ignored (coach.* in settings.yaml, then DEFAULT_PROVIDER_ID).
    llm_provider: str = Field(default="", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")

    # Vendor-specific keys (optional; used when LLM_API_KEY empty)
    stepfun_api_key: str = Field(default="", alias="STEPFUN_API_KEY")
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")
    zhipu_api_key: str = Field(default="", alias="ZHIPU_API_KEY")
    moonshot_api_key: str = Field(default="", alias="MOONSHOT_API_KEY")
    siliconflow_api_key: str = Field(default="", alias="SILICONFLOW_API_KEY")
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    minimax_api_key: str = Field(default="", alias="MINIMAX_API_KEY")
    yi_api_key: str = Field(default="", alias="YI_API_KEY")
    baichuan_api_key: str = Field(default="", alias="BAICHUAN_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Legacy xAI fields (key still supported; base URL / model ignored)
    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_base_url: str = Field(default="", alias="XAI_BASE_URL")
    xai_model: str = Field(default="", alias="XAI_MODEL")

    # GSI
    gsi_host: str = Field(default="127.0.0.1", alias="GSI_HOST")
    gsi_port: int = Field(default=3000, alias="GSI_PORT")
    gsi_auth_token: str = Field(default="dodoclaw_secret", alias="GSI_AUTH_TOKEN")
    # Write raw GSI payloads to logs/gsi/*.jsonl (for debugging / sample collection)
    gsi_record: bool = Field(default=False, alias="GSI_RECORD")

    # Voice / ASR / TTS
    stt_backend: str = Field(default="mock", alias="STT_BACKEND")
    tts_backend: str = Field(default="mock", alias="TTS_BACKEND")
    stt_model: str = Field(default="", alias="STT_MODEL")
    tts_model: str = Field(default="", alias="TTS_MODEL")
    tts_voice: str = Field(default="", alias="TTS_VOICE")
    coach_language: str = Field(default="zh-CN", alias="COACH_LANGUAGE")

    # Meta / BP
    meta_source: str = Field(default="auto", alias="META_SOURCE")  # auto|opendota|stratz
    opendota_api_key: str = Field(default="", alias="OPENDOTA_API_KEY")
    stratz_api_token: str = Field(default="", alias="STRATZ_API_TOKEN")
    # OpenDota bracket 0=all, 1-8=single
    opendota_bracket: int = Field(default=0, alias="OPENDOTA_BRACKET")
    # STRATZ: all|low|mid|high|divine_immortal|...
    stratz_bracket: str = Field(default="high", alias="STRATZ_BRACKET")

    def yaml_path(self) -> Path:
        return config_dir() / "settings.yaml"

    def load_yaml(self) -> dict[str, Any]:
        path = self.yaml_path()
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _note_ignored_env(self) -> None:
        """One info line if .env still sets provider/model/endpoint (names only)."""
        global _ignored_logged
        if _ignored_logged:
            return
        values = {
            "LLM_PROVIDER": self.llm_provider,
            "LLM_MODEL": self.llm_model,
            "LLM_BASE_URL": self.llm_base_url,
            "XAI_MODEL": self.xai_model,
            "XAI_BASE_URL": self.xai_base_url,
        }
        names = [k for k in IGNORED_ENV if (values.get(k) or "").strip()]
        if names:
            _ignored_logged = True
            logger.info(
                ".env 里的 %s 已忽略：服务商和模型只从 config\\settings.yaml 的 coach.provider / coach.model 读取",
                ", ".join(names),
            )

    def vendor_key(self, provider_id: str) -> str:
        return {
            "stepfun_plan": self.stepfun_api_key,
            "stepfun": self.stepfun_api_key,
            "deepseek": self.deepseek_api_key,
            "dashscope": self.dashscope_api_key,
            "zhipu": self.zhipu_api_key,
            "moonshot": self.moonshot_api_key,
            "siliconflow": self.siliconflow_api_key,
            "volcengine": self.ark_api_key,
            "minimax": self.minimax_api_key,
            "yi": self.yi_api_key,
            "baichuan": self.baichuan_api_key,
            "openai": self.openai_api_key,
            "xai": self.xai_api_key,
        }.get(provider_id, "")

    def resolve_llm(self) -> tuple[str, str, str, str, str]:
        """
        Returns (provider_id, provider_name, api_key, base_url, model).
        Provider / base URL / model: settings.yaml coach.* → provider defaults
        (DEFAULT_PROVIDER_ID). .env only supplies keys (PRD D9).
        """
        self._note_ignored_env()
        yaml_coach = (self.load_yaml().get("coach") or {})
        provider_id = str(yaml_coach.get("provider") or DEFAULT_PROVIDER_ID).strip()

        # Legacy: only an xAI key and no provider chosen in settings.yaml → keep xai
        if (
            not yaml_coach.get("provider")
            and not self.llm_api_key
            and not self.stepfun_api_key
            and not self.deepseek_api_key
            and self.xai_api_key
        ):
            provider_id = "xai"

        base_hint = str(yaml_coach.get("base_url") or "")
        model_hint = str(yaml_coach.get("model") or "")

        # Custom OpenAI-compatible entry (PRD D12): URL/model from the saved list;
        # key from CUSTOM_<id>_API_KEY only (never another vendor's key).
        if provider_id.strip().lower() == "custom":
            from dodoclaw.webui import customs

            cid = str(yaml_coach.get("custom_id") or "").strip()
            cp = customs.get_custom(cid) or (customs.list_customs()[:1] or [None])[0]
            if cp is not None:
                import os

                key = (os.environ.get(cp.key_env) or "").strip()
                if not key:
                    from dodoclaw.webui import keystore

                    key = (keystore.store().get(cp.key_env) or "").strip()
                return "custom", cp.display_name, key, cp.base_url, cp.model
            # orphaned custom_id → fall through to default preset
            provider_id = DEFAULT_PROVIDER_ID
            base_hint, model_hint = "", ""

        spec = get_provider(provider_id)
        # Provider's own key (Settings fields include the .env file), then the
        # generic LLM_API_KEY. Never another vendor's key (PRD D10 picker).
        vendor_key = (self.vendor_key(spec.id) or "").strip()
        spec, key, url, model = resolve_llm_runtime(
            provider_id,
            api_key=vendor_key or self.llm_api_key,
            base_url=base_hint,
            model=model_hint,
        )
        return spec.id, spec.name, key, url, model


@lru_cache
def get_settings() -> Settings:
    ensure_user_config_seeded()
    env_path = app_dir() / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


def project_root() -> Path:
    return app_dir()


def resolve_dota_cfg_target() -> Path | None:
    from dodoclaw.gsi_install import resolve_dota_cfg_target as _resolve

    return _resolve()


def save_env_value(key: str, value: str) -> Path:
    """Upsert a KEY=value in the portable .env next to the app."""
    ensure_runtime_dirs()
    path = app_dir() / ".env"
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    found = False
    out: list[str] = []
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or (
            stripped.startswith("#") and stripped[1:].lstrip().startswith(prefix)
        ):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value
    reload_settings()
    return path


def save_env_values(pairs: dict[str, str]) -> Path:
    path = app_dir() / ".env"
    for k, v in pairs.items():
        path = save_env_value(k, v)
    return path


def save_coach_choice(provider_id: str, model: str = "", base_url: str = "") -> Path:
    """Write coach.provider / model / base_url into config/settings.yaml (PRD D9:
    the provider choice lives there, not in .env). Only those lines of the
    ``coach:`` block change; comments and everything else are kept.
    Empty model / base_url removes the override (provider default)."""
    import re

    path = config_dir() / "settings.yaml"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    start = next((i for i, ln in enumerate(lines) if re.match(r"^coach\s*:", ln)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("coach:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
        end += 1
    want = {"provider": provider_id, "model": model, "base_url": base_url}
    block = lines[start + 1 : end]
    out: list[str] = []
    for ln in block:
        m = re.match(r"^(\s+)(provider|model|base_url)\s*:", ln)
        if m and m.group(2) in want:
            name, val = m.group(2), want.pop(m.group(2))
            if val:
                out.append(f'{m.group(1)}{name}: "{val}"')
            continue
        out.append(ln)
    new = [f'  {k}: "{v}"' for k, v in want.items() if v]
    lines[start + 1 : end] = new + out
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    reload_settings()
    return path
