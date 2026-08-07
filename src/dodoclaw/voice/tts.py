from __future__ import annotations

import abc
import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class TextToSpeech(abc.ABC):
    @abc.abstractmethod
    def speak(self, text: str) -> None:
        raise NotImplementedError


class MockTTS(TextToSpeech):
    def speak(self, text: str) -> None:
        print(f"🔊 [mock TTS] {text}")


class EdgeTTS(TextToSpeech):
    """Microsoft Edge online TTS (optional: edge-tts + pygame)."""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        self.voice = voice
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            raise ImportError("Edge TTS needs: pip install edge-tts pygame") from exc

    def speak(self, text: str) -> None:
        if not text.strip():
            return
        import edge_tts

        from dodoclaw.voice.audio_io import play_audio_file

        async def _gen(path: Path) -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(path))

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            asyncio.run(_gen(out))
            play_audio_file(out)
        finally:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass


class StepFunTTS(TextToSpeech):
    """
    StepFun TTS (OpenAI-compatible audio.speech).
    Step Plan: POST https://api.stepfun.com/step_plan/v1/audio/speech
    Model: stepaudio-2.5-tts
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stepfun.com/step_plan/v1",
        model: str = "stepaudio-2.5-tts",
        voice: str = "cixingnansheng",
        instruction: str = "语速适中，口齿清晰，适合游戏内语音播报。",
    ) -> None:
        if not api_key:
            raise RuntimeError("StepFun TTS 需要 API Key（STEPFUN_API_KEY / LLM_API_KEY）")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.instruction = instruction

    def speak(self, text: str) -> None:
        if not (text or "").strip():
            return
        # API max ~1000 chars for input
        text = text.strip()
        if len(text) > 900:
            text = text[:899] + "…"

        from openai import OpenAI

        from dodoclaw.voice.audio_io import play_audio_file

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=45.0)
        extra = {}
        if self.model.startswith("stepaudio-2.5") and self.instruction:
            extra["instruction"] = self.instruction

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            out = Path(tmp.name)

        try:
            try:
                with client.audio.speech.with_streaming_response.create(
                    model=self.model,
                    voice=self.voice,
                    input=text,
                    response_format="mp3",
                    extra_body=extra or None,
                ) as response:
                    response.stream_to_file(out)
            except Exception:
                logger.debug("streaming speech failed; non-stream", exc_info=True)
                response = client.audio.speech.create(
                    model=self.model,
                    voice=self.voice,
                    input=text,
                    response_format="mp3",
                    extra_body=extra or None,
                )
                data = getattr(response, "content", None)
                if data is None and hasattr(response, "read"):
                    data = response.read()
                if data is None and hasattr(response, "stream_to_file"):
                    response.stream_to_file(out)
                    data = b""
                if data:
                    out.write_bytes(data)

            if out.stat().st_size < 32:
                raise RuntimeError("TTS 返回空音频（检查模型/音色/额度）")
            play_audio_file(out)
        finally:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass


def create_tts(
    backend: str = "mock",
    *,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    voice: str = "",
) -> TextToSpeech:
    from dodoclaw.audio_providers import get_tts_backend

    spec = get_tts_backend(backend)
    bid = spec.id
    if bid == "mock":
        return MockTTS()
    if bid == "edge":
        return EdgeTTS(voice=voice or model or spec.default_model or "zh-CN-XiaoxiaoNeural")
    if bid in {"stepfun_plan", "stepfun"}:
        return StepFunTTS(
            api_key=api_key,
            base_url=base_url or spec.base_url,
            model=model or spec.default_model,
            voice=voice or (spec.voices[0] if spec.voices else "cixingnansheng"),
        )
    raise ValueError(f"Unknown TTS backend: {backend}")
