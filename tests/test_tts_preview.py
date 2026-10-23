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
