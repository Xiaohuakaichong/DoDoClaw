from __future__ import annotations

import abc
import base64
import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SpeechToText(Protocol):
    def listen_once(self, seconds: float = 5.0) -> str: ...


class BaseSTT(abc.ABC):
    @abc.abstractmethod
    def listen_once(self, seconds: float = 5.0) -> str:
        raise NotImplementedError


class MockSTT(BaseSTT):
    """Interactive fallback: type what you would have said."""

    def listen_once(self, seconds: float = 5.0) -> str:
        try:
            return input("🎤 [mock STT] 输入你的问题（回车发送，空行跳过）: ").strip()
        except EOFError:
            return ""


def dota_initial_prompt(max_chars: int = 800) -> str:
    """Hero / item alias string for Whisper initial_prompt (Dota顾问)."""
    try:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "data" / "hero_aliases.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        heroes = data.get("heroes") or []
        parts: list[str] = ["刀塔，英雄："]
        for h in heroes:
            names = [h.get("name_zh") or ""] + list(h.get("aliases") or [])
            names = [n for n in names if n]
            if names:
                parts.append("/".join(names[:4]))
        prompt = "，".join(parts)
        return prompt[:max_chars]
    except Exception:
        logger.exception("build dota initial_prompt failed")
        return "刀塔 英雄 技能 出装"


class WhisperSTT(BaseSTT):
    """Local faster-whisper STT (optional dependency). CPU int8.

    Model weights download on first use (see webui.whisper_model); they are not
    bundled in the exe.
    """

    def __init__(self, model_size: str = "base", sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.model_size = model_size or "base"
        try:
            from faster_whisper import WhisperModel  # type: ignore
            import sounddevice as sd
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "Whisper STT needs: pip install faster-whisper sounddevice numpy"
            ) from exc

        self._sd = sd
        self._np = np
        self._WhisperModel = WhisperModel
        self._model = None
        self._initial_prompt = dota_initial_prompt()

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        from dodoclaw.webui import whisper_model

        if not whisper_model.ensure_ready(timeout=600.0):
            raise RuntimeError(whisper_model.status().get("error_zh") or "模型未就绪")
        # Cache dir so faster-whisper / CTranslate2 find the snapshot
        import os

        os.environ.setdefault("HF_HOME", str(whisper_model.model_dir()))
        logger.info("Loading Whisper model: %s (cpu int8)", self.model_size)
        self._model = self._WhisperModel(
            self.model_size, device="cpu", compute_type="int8",
            download_root=str(whisper_model.model_dir()),
        )
        return self._model

    def listen_once(self, seconds: float = 5.0) -> str:
        model = self._ensure_model()
        logger.info("Recording %.1fs...", seconds)
        audio = self._sd.rec(
            int(seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        )
        self._sd.wait()
        samples = audio[:, 0]
        segments, _info = model.transcribe(
            samples,
            language="zh",
            beam_size=1,
            initial_prompt=self._initial_prompt,
        )
        text = "".join(seg.text for seg in segments).strip()
        logger.info("STT: %s", text)
        return text

    def transcribe_array(self, samples, *, language: str = "zh") -> str:
        """Transcribe a float32 mono array (for offline verification)."""
        model = self._ensure_model()
        segments, _info = model.transcribe(
            samples,
            language=language,
            beam_size=1,
            initial_prompt=self._initial_prompt,
        )
        return "".join(seg.text for seg in segments).strip()


class StepFunSTT(BaseSTT):
    """
    StepFun ASR via Step Plan / standard API.

    Preferred: OpenAI-compatible POST /audio/transcriptions
    Fallback:  POST /audio/asr/sse (base64 PCM + SSE)
    Docs: https://platform.stepfun.com/docs/zh/step-plan/integrations/audio-api
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stepfun.com/step_plan/v1",
        model: str = "stepaudio-2.5-asr",
        sample_rate: int = 16000,
        language: str = "zh",
    ) -> None:
        if not api_key:
            raise RuntimeError("StepFun STT 需要 API Key（STEPFUN_API_KEY / LLM_API_KEY）")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sample_rate = sample_rate
        self.language = language

    def listen_once(self, seconds: float = 5.0) -> str:
        from dodoclaw.voice.audio_io import record_wav

        wav_path = record_wav(seconds=seconds, sample_rate=self.sample_rate)
        try:
            text = self._transcribe_file(wav_path)
            if not text:
                text = self._transcribe_sse_pcm(wav_path)
            logger.info("StepFun STT: %s", text)
            return text.strip()
        finally:
            wav_path.unlink(missing_ok=True)

    def _transcribe_file(self, wav_path) -> str:
        """OpenAI-compatible transcriptions endpoint."""
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            with open(wav_path, "rb") as f:
                # response_format is required by StepFun docs
                result = client.audio.transcriptions.create(
                    model=self.model,
                    file=f,
                    response_format="json",
                )
            if isinstance(result, str):
                return result
            return (getattr(result, "text", None) or str(result) or "").strip()
        except Exception:
            logger.exception("transcriptions API failed; will try asr/sse")
            return ""

    def _transcribe_sse_pcm(self, wav_path) -> str:
        """Step Plan ASR SSE: /audio/asr/sse with base64 audio."""
        import wave

        import httpx

        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            pcm = wf.readframes(wf.getnframes())

        b64 = base64.b64encode(pcm).decode("ascii")
        payload = {
            "audio": {
                "data": b64,
                "input": {
                    "transcription": {
                        "model": self.model,
                        "language": self.language,
                        "enable_itn": True,
                    },
                    "format": {
                        "type": "pcm",
                        "codec": "pcm_s16le",
                        "rate": rate,
                        "bits": sw * 8,
                        "channel": nch,
                    },
                },
            }
        }
        url = f"{self.base_url}/audio/asr/sse"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        final_text = ""
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:].strip()
                    else:
                        continue
                    if data_str in {"[DONE]", ""}:
                        continue
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    et = event.get("type")
                    if et == "transcript.text.done":
                        final_text = event.get("text") or final_text
                    elif et == "transcript.text.delta":
                        final_text += event.get("delta") or ""
                    elif et == "error":
                        raise RuntimeError(event.get("message") or "ASR error")
        return final_text.strip()


class SiliconFlowSTT(BaseSTT):
    """SiliconFlow OpenAI-compatible POST /v1/audio/transcriptions.

    Model: FunAudioLLM/SenseVoiceSmall. Docs list only ``file`` + ``model`` —
    no prompt / hotwords field, so aliases are not sent.
    Limit: ≤50MB / ≤1 hour.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.siliconflow.cn/v1",
        model: str = "FunAudioLLM/SenseVoiceSmall",
        sample_rate: int = 16000,
    ) -> None:
        if not api_key:
            raise RuntimeError("硅基流动语音识别需要 API Key（SILICONFLOW_API_KEY）")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model or "FunAudioLLM/SenseVoiceSmall"
        self.sample_rate = sample_rate

    def listen_once(self, seconds: float = 5.0) -> str:
        from dodoclaw.voice.audio_io import record_wav

        wav_path = record_wav(seconds=seconds, sample_rate=self.sample_rate)
        try:
            return self._transcribe_file(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)

    def _transcribe_file(self, wav_path) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=60.0, max_retries=0)
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(model=self.model, file=f)
        if isinstance(result, str):
            return result.strip()
        return (getattr(result, "text", None) or str(result) or "").strip()


def create_stt(
    backend: str = "mock",
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    sample_rate: int = 16000,
) -> BaseSTT:
    from dodoclaw.audio_providers import get_stt_backend

    spec = get_stt_backend(backend)
    bid = spec.id
    if bid == "mock":
        return MockSTT()
    if bid == "whisper":
        return WhisperSTT(model_size=model or spec.default_model or "base", sample_rate=sample_rate)
    if bid in {"stepfun_plan", "stepfun"}:
        return StepFunSTT(
            api_key=api_key,
            base_url=base_url or spec.base_url,
            model=model or spec.default_model,
            sample_rate=sample_rate,
        )
    if bid == "siliconflow":
        return SiliconFlowSTT(
            api_key=api_key,
            base_url=base_url or spec.base_url,
            model=model or spec.default_model,
            sample_rate=sample_rate,
        )
    raise ValueError(f"Unknown STT backend: {backend}")
