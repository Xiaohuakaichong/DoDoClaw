"""Mic capture and simple audio playback helpers."""

from __future__ import annotations

import logging
import tempfile
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def record_wav(seconds: float = 5.0, sample_rate: int = 16000) -> Path:
    """Record mono 16-bit PCM WAV to a temp file; returns path."""
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as exc:
        raise ImportError("录音需要: pip install sounddevice numpy") from exc

    frames = int(seconds * sample_rate)
    logger.info("Recording %.1fs @ %dHz…", seconds, sample_rate)
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    samples = np.clip(audio[:, 0], -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    path = Path(tmp.name)
    tmp.close()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path


def record_pcm16(seconds: float = 5.0, sample_rate: int = 16000) -> bytes:
    """Return raw little-endian PCM s16le mono bytes."""
    path = record_wav(seconds=seconds, sample_rate=sample_rate)
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.readframes(wf.getnframes())
    finally:
        path.unlink(missing_ok=True)


def play_audio_file(path: Path) -> None:
    """Play mp3/wav via pygame if available; else best-effort OS open."""
    path = Path(path)
    if not path.exists():
        return
    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(40)
        return
    except Exception:
        logger.debug("pygame playback unavailable", exc_info=True)

    # Windows fallback for wav
    if path.suffix.lower() == ".wav":
        try:
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        except Exception:
            logger.debug("winsound failed", exc_info=True)

    logger.warning("无法播放音频，文件已保存: %s", path)
