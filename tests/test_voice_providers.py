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
