from __future__ import annotations

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


def _env_file() -> str:
    return str(app_dir() / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Unified LLM settings
    llm_provider: str = Field(default=DEFAULT_PROVIDER_ID, alias="LLM_PROVIDER")
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

    # Legacy xAI fields (still supported)
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

    def resolve_llm(self) -> tuple[str, str, str, str, str]:
        """
        Returns (provider_id, provider_name, api_key, base_url, model).
        Honors legacy XAI_* when provider is xai or only xai key is set.
        """
        yaml_coach = (self.load_yaml().get("coach") or {})
        provider_id = (
            self.llm_provider
            or yaml_coach.get("provider")
            or DEFAULT_PROVIDER_ID
        ).strip()

        # If user only has legacy XAI config and never set provider, keep xai
        if (
            (not self.llm_provider or self.llm_provider == DEFAULT_PROVIDER_ID)
            and not self.llm_api_key
            and not self.stepfun_api_key
            and self.xai_api_key
            and not yaml_coach.get("provider")
        ):
            # Only auto-switch when default would leave them without a key for stepfun
            if not self.stepfun_api_key and not self.llm_api_key:
                provider_id = "xai"

        api_key_hint = self.llm_api_key
        base_hint = self.llm_base_url
        model_hint = self.llm_model

        # Legacy xAI overrides when provider is xai
        if get_provider(provider_id).id == "xai":
            api_key_hint = api_key_hint or self.xai_api_key
            base_hint = base_hint or self.xai_base_url
            model_hint = model_hint or self.xai_model

        # yaml optional overrides
        base_hint = base_hint or str(yaml_coach.get("base_url") or "")
        model_hint = model_hint or str(yaml_coach.get("model") or "")

        spec, key, url, model = resolve_llm_runtime(
            provider_id,
            api_key=api_key_hint,
            base_url=base_hint,
            model=model_hint,
        )

        # Vendor-specific keys from Settings fields
        if not key:
            vendor_map = {
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
            }
            key = (vendor_map.get(spec.id) or "").strip() or key

        if not key and self.xai_api_key and spec.id == "xai":
            key = self.xai_api_key

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
