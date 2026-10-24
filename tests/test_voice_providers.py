"""PM D13: coach / STT / TTS each pick their own backend; Key reuse; no Key in voice cards."""

from __future__ import annotations

from pathlib import Path

import pytest

from dodoclaw import config
from dodoclaw.audio_providers import get_tts_backend, list_tts_backends
from dodoclaw.voice.tts import SiliconFlowTTS, create_tts


def test_siliconflow_tts_preset():
    t = get_tts_backend("siliconflow")
    assert t.default_model == "FunAudioLLM/CosyVoice2-0.5B"
    assert t.key_from_llm_provider == "siliconflow"
    assert "anna" in t.voices and t.voices[0] == "anna"
    assert {"edge", "stepfun", "siliconflow", "mock"} <= {b.id for b in list_tts_backends()}


def test_siliconflow_tts_voice_prefix():
    t = SiliconFlowTTS(api_key="sk-x", voice="anna")
    assert t.voice == "FunAudioLLM/CosyVoice2-0.5B:anna"
    t2 = SiliconFlowTTS(api_key="sk-x", voice="FunAudioLLM/CosyVoice2-0.5B:bella")
    assert t2.voice.endswith(":bella")


def test_save_voice_choice_keeps_comments(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    y = cfg / "settings.yaml"
    y.write_text(
        '# keep\nvoice:\n  # ASR note\n  stt_backend: "mock"\n  sample_rate: 16000\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "config_dir", lambda: cfg)
    monkeypatch.setattr(config, "reload_settings", lambda: None)
    config.save_voice_choice(stt_backend="whisper", tts_backend="edge")
    text = y.read_text(encoding="utf-8")
    assert '# keep' in text and '# ASR note' in text and 'sample_rate: 16000' in text
    assert 'stt_backend: "whisper"' in text and 'tts_backend: "edge"' in text


# ── 云端试听（mock）─────────────────────────────────────────
class _AuthErr(Exception):
    status_code = 401


def test_preview_cloud_ok_auth_timeout(monkeypatch):
    import time

    from dodoclaw.coach import errors
    from dodoclaw.webui import tts_preview as tp

    played = []
    monkeypatch.setattr(tp, "_default_player", lambda p: played.append(p))

    class Ok:
        def synthesize(self, text, out, timeout=45.0):
            Path(out).write_bytes(b"x" * 64)

    class Bad:
        def synthesize(self, text, out, timeout=45.0):
            raise _AuthErr("invalid api key sk-SECRET")

    class Slow:
        def synthesize(self, text, out, timeout=45.0):
            time.sleep(2.0)

    assert tp.preview_cloud(Ok()) == {"ok": True, "msg": ""} and played
    r = tp.preview_cloud(Bad())
    assert r == {"ok": False, "msg": errors.AUTH} and "SECRET" not in r["msg"]
    monkeypatch.setattr(tp, "SYNTH_TIMEOUT", 0.1)
    assert tp.preview_cloud(Slow()) == {"ok": False, "msg": tp.MSG_TIMEOUT}

    class SdkTimeout(Exception):
        pass

    SdkTimeout.__name__ = "APITimeoutError"

    class TimesOut:
        def synthesize(self, text, out, timeout=45.0):
            raise SdkTimeout("Request timed out.")

    time.sleep(2.1)  # let the abandoned Slow thread finish
    assert tp.preview_cloud(TimesOut()) == {"ok": False, "msg": tp.MSG_TIMEOUT}


def test_cloud_tts_synthesize_writes_file(monkeypatch, tmp_path):
    import openai

    calls = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def stream_to_file(self, out): Path(out).write_bytes(b"x" * 64)

    class Client:
        def __init__(self, **kw):
            calls.update(kw)
            self.audio = type("A", (), {"speech": type("S", (), {
                "with_streaming_response": type("W", (), {"create": staticmethod(lambda **k: calls.update(req=k) or Resp())})()})()})()

    monkeypatch.setattr(openai, "OpenAI", Client)
    out = tmp_path / "a.mp3"
    SiliconFlowTTS(api_key="sk-x", voice="anna").synthesize("你好", out, timeout=20.0)
    assert out.stat().st_size == 64 and calls["timeout"] == 20.0 and calls["max_retries"] == 0
    assert calls["req"]["voice"] == "FunAudioLLM/CosyVoice2-0.5B:anna" and calls["req"]["response_format"] == "mp3"
