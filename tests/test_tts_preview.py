"""试听 works with 播报 off, and every failure has a specific Chinese reason (edge_tts mocked)."""

from __future__ import annotations

import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest

from dodoclaw.webui import tts_preview as tp
from dodoclaw.webui.app import Bridge


def _edge(exc: BaseException | None = None, data: bytes = b"ID3" + b"\0" * 64, seen: list | None = None):
    class Communicate:
        def __init__(self, text, voice):
            if seen is not None:
                seen.append((text, voice))

        async def save(self, path):
            if exc is not None:
                raise exc
            Path(path).write_bytes(data)

    return SimpleNamespace(Communicate=Communicate)


def test_preview_synthesizes_selected_voice_and_plays():
    seen, played = [], []
    r = tp.preview("zh-CN-YunxiNeural", edge_module=_edge(seen=seen), player=lambda p: played.append(p.read_bytes()[:3]))
    assert r == {"ok": True, "msg": ""}
    assert seen[0][1] == "zh-CN-YunxiNeural" and played == [b"ID3"]


def test_temp_file_removed():
    paths = []
    tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(), player=paths.append)
    assert paths and not paths[0].exists()


def test_edge_not_installed(monkeypatch):
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "edge_tts":
            raise ImportError("no edge_tts")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(tp.importlib, "import_module", lambda n: fake_import(n))
    assert tp.preview(tp.DEFAULT_VOICE, player=lambda p: None) == {"ok": False, "msg": "没装语音合成组件，试听不了"}


class ClientConnectorError(Exception):  # stands in for aiohttp's error class
    pass


@pytest.mark.parametrize("exc", [OSError("dns"), TimeoutError(), ClientConnectorError("x")])
def test_network_failure(exc):
    r = tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(exc), player=lambda p: None)
    assert r == {"ok": False, "msg": "联网失败，稍后再试"}


def test_empty_audio_counts_as_network():
    r = tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(data=b""), player=lambda p: None)
    assert r["msg"] == "联网失败，稍后再试"


def test_no_player_and_playback_error():
    def no_pygame(_p):
        raise ImportError("pygame")

    def broken(_p):
        raise RuntimeError("no device")

    assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(), player=no_pygame)["msg"] == "没装播放组件，试听不了"
    assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(), player=broken)["msg"] == "没能播放声音，检查一下音频输出设备"


def test_unknown_synth_error():
    r = tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(ValueError("bad")), player=lambda p: None)
    assert r == {"ok": False, "msg": "试听失败，详情见日志"}


def test_busy_while_playing():
    tp._lock.acquire()
    try:
        assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge(), player=lambda p: None)["msg"] == tp.MSG_BUSY
    finally:
        tp._lock.release()


def test_voice_choice():
    assert tp.edge_voice("") == tp.DEFAULT_VOICE
    assert tp.edge_voice("cixingnansheng") == tp.DEFAULT_VOICE  # StepFun voice id -> Edge default
    assert tp.edge_voice("zh-CN-YunxiNeural") == "zh-CN-YunxiNeural"
    assert tp.voice_label(tp.DEFAULT_VOICE) == "Edge 免费声音 · 晓晓（女声）"


@pytest.mark.parametrize("backend", ["mock", "edge"])
def test_bridge_preview_ignores_tts_switch(monkeypatch, backend):
    calls = []
    monkeypatch.setattr(tp, "preview", lambda voice, **kw: calls.append(voice) or {"ok": True, "msg": ""})
    b = Bridge.__new__(Bridge)
    b._svc = SimpleNamespace(tts_backend=backend, tts_voice="")
    assert b.preview_tts() == {"ok": True, "msg": ""}
    assert calls == [tp.DEFAULT_VOICE]


def test_bridge_preview_never_raises(monkeypatch):
    def boom(voice, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(tp, "preview", boom)
    b = Bridge.__new__(Bridge)
    b._svc = SimpleNamespace(tts_backend="mock", tts_voice="")
    assert b.preview_tts() == {"ok": False, "msg": "试听失败，详情见日志"}


# ── playback backends (pygame -> Windows MCI) ─────────────
from dodoclaw.voice import audio_io  # noqa: E402


@pytest.fixture
def no_pygame(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "pygame", None)  # import pygame -> ImportError


def test_play_audio_falls_back_to_mci_on_windows(no_pygame, monkeypatch, tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3" + b"\0" * 64)
    cmds = []
    monkeypatch.setattr(audio_io, "_is_windows", lambda: True)
    monkeypatch.setattr(audio_io, "_mci_send", lambda c: cmds.append(c) or 0)
    audio_io.play_audio(f)
    assert cmds[0].startswith(f'open "{f}" type mpegvideo alias ')
    assert cmds[1].startswith("play ") and cmds[1].endswith(" wait") and cmds[2].startswith("close ")


def test_preview_uses_mci_when_pygame_missing_on_windows(no_pygame, monkeypatch):
    cmds = []
    monkeypatch.setattr(audio_io, "_is_windows", lambda: True)
    monkeypatch.setattr(audio_io, "_mci_send", lambda c: cmds.append(c) or 0)
    assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge()) == {"ok": True, "msg": ""}
    assert [c.split()[0] for c in cmds] == ["open", "play", "close"]


def test_preview_mci_error_is_play_fail(no_pygame, monkeypatch):
    cmds = []
    monkeypatch.setattr(audio_io, "_is_windows", lambda: True)
    monkeypatch.setattr(audio_io, "_mci_send", lambda c: cmds.append(c) or (263 if c.startswith("play") else 0))
    assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge())["msg"] == tp.MSG_PLAY_FAIL
    assert cmds[-1].startswith("close ")  # alias always closed


def test_preview_no_player_off_windows_without_pygame(no_pygame, monkeypatch):
    monkeypatch.setattr(audio_io, "_is_windows", lambda: False)
    monkeypatch.setattr(audio_io, "_mci_send", lambda c: pytest.fail("MCI must not be used off Windows"))
    assert tp.preview(tp.DEFAULT_VOICE, edge_module=_edge()) == {"ok": False, "msg": "没装播放组件，试听不了"}


def test_play_audio_file_never_raises(no_pygame, monkeypatch, tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    monkeypatch.setattr(audio_io, "_is_windows", lambda: False)
    audio_io.play_audio_file(f)  # logs a warning, no exception


def test_stuck_synth_times_out_as_network_error(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from dodoclaw.webui import tts_preview

    class Stuck:
        def __init__(self, text, voice):
            pass

        async def save(self, path):
            await asyncio.sleep(30)

    monkeypatch.setattr(tts_preview, "SYNTH_TIMEOUT", 0.05)
    r = tts_preview.preview("zh-CN-XiaoxiaoNeural", edge_module=SimpleNamespace(Communicate=Stuck), player=lambda p: None)
    assert r == {"ok": False, "msg": tts_preview.MSG_NETWORK}
