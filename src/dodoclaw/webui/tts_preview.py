"""Settings-page 试听: synthesize one line with Edge TTS and play it.

Independent of the global TTS switch (works while 播报 is off / mock). Every failure
maps to a specific Chinese reason so the button is never a dead click.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
PREVIEW_TEXT = "肉山快复活了，准备好团战。"
VOICE_ZH = {
    "zh-CN-XiaoxiaoNeural": "晓晓（女声）",
    "zh-CN-XiaoyiNeural": "晓伊（女声）",
    "zh-CN-YunxiNeural": "云希（男声）",
    "zh-CN-YunjianNeural": "云健（男声）",
    "zh-CN-YunyangNeural": "云扬（男声）",
}

MSG_NO_EDGE = "没装语音合成组件，试听不了"
MSG_NETWORK = "联网失败，稍后再试"
MSG_NO_PLAYER = "没装播放组件，试听不了"
MSG_PLAY_FAIL = "没能播放声音，检查一下音频输出设备"
MSG_BUSY = "正在试听，等这句放完"
MSG_UNKNOWN = "试听失败，详情见日志"

_lock = threading.Lock()


def edge_voice(configured: str | None) -> str:
    """Edge voice to preview: the configured one if it is an Edge voice, else the default."""
    v = (configured or "").strip()
    return v if v.endswith("Neural") else DEFAULT_VOICE


def voice_label(voice: str) -> str:
    return f"Edge 免费声音 · {VOICE_ZH.get(voice, voice)}"


def _is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    names = {c.__name__ for c in type(exc).__mro__}
    mods = {(c.__module__ or "").split(".", 1)[0] for c in type(exc).__mro__}
    # aiohttp client errors, edge_tts WebSocketError / NoAudioReceived
    return bool(
        names & {"ClientError", "WebSocketError", "NoAudioReceived", "ClientConnectorError", "WSServerHandshakeError"}
        or "aiohttp" in mods
    )


def _pygame_play(path: Path) -> None:
    import pygame  # ImportError -> MSG_NO_PLAYER

    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(40)
    try:
        pygame.mixer.music.unload()
    except Exception:  # older pygame
        pass


def preview(
    voice: str,
    text: str = PREVIEW_TEXT,
    *,
    edge_module: Any = None,
    player: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """Returns {ok, msg}. msg is a Chinese reason when ok is False."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "msg": MSG_BUSY}
    try:
        if edge_module is None:
            try:
                edge_module = importlib.import_module("edge_tts")
            except ImportError:
                return {"ok": False, "msg": MSG_NO_EDGE}
        player = player or _pygame_play

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            out = Path(tmp.name)
        try:
            try:
                asyncio.run(edge_module.Communicate(text, voice).save(str(out)))
                if not out.exists() or out.stat().st_size < 32:
                    raise ConnectionError("empty audio")
            except Exception as exc:
                logger.warning("tts preview synth failed: %s", type(exc).__name__)
                return {"ok": False, "msg": MSG_NETWORK if _is_network_error(exc) else MSG_UNKNOWN}
            try:
                player(out)
            except ImportError:
                return {"ok": False, "msg": MSG_NO_PLAYER}
            except Exception as exc:
                logger.warning("tts preview playback failed: %s", type(exc).__name__)
                return {"ok": False, "msg": MSG_PLAY_FAIL}
            return {"ok": True, "msg": ""}
        finally:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
    finally:
        _lock.release()
