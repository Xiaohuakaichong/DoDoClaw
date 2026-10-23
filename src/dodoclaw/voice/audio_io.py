"""Mic capture and simple audio playback helpers."""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
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


class PlaybackUnavailable(RuntimeError):
    """No playback backend on this machine (no pygame, and not Windows for MCI)."""


def _is_windows() -> bool:
    return os.name == "nt"


def _play_pygame(path: Path) -> None:
    import pygame  # ImportError when not installed (e.g. Python 3.14)

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(40)
    try:
        pygame.mixer.music.unload()  # release the file so the temp copy can be deleted
    except Exception:
        pass


def _mci_send(command: str) -> int:
    """winmm.mciSendStringW; returns the MCI error code (0 = ok)."""
    import ctypes

    return int(ctypes.windll.winmm.mciSendStringW(command, None, 0, None))


def _play_mci(path: Path) -> None:
    """Blocking playback through Windows MCI (mp3 via mpegvideo, wav via waveaudio)."""
    kind = "mpegvideo" if path.suffix.lower() == ".mp3" else "waveaudio"
    alias = f"dodoclaw_{uuid.uuid4().hex[:8]}"
    err = _mci_send(f'open "{path}" type {kind} alias {alias}')
    if err:
        raise RuntimeError(f"MCI open failed ({err})")
    try:
        err = _mci_send(f"play {alias} wait")
        if err:
            raise RuntimeError(f"MCI play failed ({err})")
    finally:
        _mci_send(f"close {alias}")


def play_audio(path: Path) -> None:
    """Play mp3/wav, blocking. pygame first, then Windows MCI.

    Raises PlaybackUnavailable when neither backend exists, RuntimeError when a
    backend exists but playback failed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    pygame_missing = False
    try:
        _play_pygame(path)
        return
    except ImportError:
        pygame_missing = True
        logger.debug("pygame not installed")
    except Exception:
        logger.debug("pygame playback failed", exc_info=True)
    if _is_windows():
        _play_mci(path)
        return
    if pygame_missing:
        raise PlaybackUnavailable("no pygame and no Windows MCI")
    raise RuntimeError("pygame playback failed")


def play_audio_file(path: Path) -> None:
    """Best-effort playback (never raises); used by the TTS backends."""
    try:
        play_audio(path)
    except Exception as exc:
        logger.warning("无法播放音频（%s）: %s", type(exc).__name__, path)
