"""Selectable ASR / TTS backends (local + CN cloud, Step Plan audio)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioBackendSpec:
    id: str
    name: str
    kind: str  # stt | tts
    default_model: str = ""
    models: tuple[str, ...] = ()
    # Reuse LLM provider key resolution
    key_from_llm_provider: str = ""  # e.g. stepfun_plan
    base_url: str = ""
    note: str = ""
    voices: tuple[str, ...] = ()  # TTS only


STT_BACKENDS: dict[str, AudioBackendSpec] = {
    "mock": AudioBackendSpec(
        id="mock",
        name="Mock（打字模拟）",
        kind="stt",
        note="开发/无麦克风时用文本代替语音",
    ),
    "whisper": AudioBackendSpec(
        id="whisper",
        name="本地 Whisper（faster-whisper）",
        kind="stt",
        default_model="base",
        models=("tiny", "base", "small", "medium"),
        note="完全本地，需 pip install faster-whisper",
    ),
    "stepfun_plan": AudioBackendSpec(
        id="stepfun_plan",
        name="阶跃 Step Plan ASR",
        kind="stt",
        default_model="stepaudio-2.5-asr",
        models=("stepaudio-2.5-asr", "step-asr"),
        key_from_llm_provider="stepfun_plan",
        base_url="https://api.stepfun.com/step_plan/v1",
        note="Coding Plan 额度 · stepaudio-2.5-asr（见官方 audio-api 文档）",
    ),
    "stepfun": AudioBackendSpec(
        id="stepfun",
        name="阶跃标准 API ASR",
        kind="stt",
        default_model="stepaudio-2.5-asr",
        models=("stepaudio-2.5-asr", "step-asr"),
        key_from_llm_provider="stepfun",
        base_url="https://api.stepfun.com/v1",
        note="按量计费开放平台 /v1",
    ),
}

TTS_BACKENDS: dict[str, AudioBackendSpec] = {
    "mock": AudioBackendSpec(
        id="mock",
        name="Mock（只打印文字）",
        kind="tts",
        note="不播语音，适合调试",
    ),
    "edge": AudioBackendSpec(
        id="edge",
        name="Edge TTS（微软在线）",
        kind="tts",
        default_model="zh-CN-XiaoxiaoNeural",
        models=(
            "zh-CN-XiaoxiaoNeural",
            "zh-CN-YunxiNeural",
            "zh-CN-YunyangNeural",
            "zh-CN-XiaoyiNeural",
        ),
        note="免费在线，需 edge-tts + pygame",
        voices=(
            "zh-CN-XiaoxiaoNeural",
            "zh-CN-YunxiNeural",
            "zh-CN-YunyangNeural",
        ),
    ),
    "stepfun_plan": AudioBackendSpec(
        id="stepfun_plan",
        name="阶跃 Step Plan TTS",
        kind="tts",
        default_model="stepaudio-2.5-tts",
        models=("stepaudio-2.5-tts", "step-tts-mini", "step-tts-2"),
        key_from_llm_provider="stepfun_plan",
        base_url="https://api.stepfun.com/step_plan/v1",
        note="Coding Plan 额度 · /step_plan/v1/audio/speech",
        voices=(
            "cixingnansheng",
            "linjiajiejie",
            "zhengpaiqingnian",
            "yuanqishaonv",
            "wenrounansheng",
        ),
    ),
    "stepfun": AudioBackendSpec(
        id="stepfun",
        name="阶跃标准 API TTS",
        kind="tts",
        default_model="stepaudio-2.5-tts",
        models=("stepaudio-2.5-tts", "step-tts-mini", "step-tts-2"),
        key_from_llm_provider="stepfun",
        base_url="https://api.stepfun.com/v1",
        note="按量计费 /v1/audio/speech",
        voices=(
            "cixingnansheng",
            "linjiajiejie",
            "zhengpaiqingnian",
            "yuanqishaonv",
            "wenrounansheng",
        ),
    ),
}

DEFAULT_STT = "mock"
DEFAULT_TTS = "mock"


def get_stt_backend(backend_id: str | None) -> AudioBackendSpec:
    key = (backend_id or DEFAULT_STT).strip().lower()
    aliases = {
        "faster-whisper": "whisper",
        "step-plan": "stepfun_plan",
        "step_plan": "stepfun_plan",
        "stepfun-asr": "stepfun_plan",
    }
    key = aliases.get(key, key)
    return STT_BACKENDS.get(key, STT_BACKENDS[DEFAULT_STT])


def get_tts_backend(backend_id: str | None) -> AudioBackendSpec:
    key = (backend_id or DEFAULT_TTS).strip().lower()
    aliases = {
        "edge-tts": "edge",
        "step-plan": "stepfun_plan",
        "step_plan": "stepfun_plan",
        "stepfun-tts": "stepfun_plan",
    }
    key = aliases.get(key, key)
    return TTS_BACKENDS.get(key, TTS_BACKENDS[DEFAULT_TTS])


def list_stt_backends() -> list[AudioBackendSpec]:
    return list(STT_BACKENDS.values())


def list_tts_backends() -> list[AudioBackendSpec]:
    return list(TTS_BACKENDS.values())
