from dodoclaw.audio_providers import get_stt_backend, get_tts_backend, list_stt_backends
from dodoclaw.voice.stt import create_stt
from dodoclaw.voice.tts import create_tts


def test_stepfun_plan_audio_presets():
    stt = get_stt_backend("stepfun_plan")
    tts = get_tts_backend("stepfun_plan")
    assert "step_plan" in stt.base_url
    assert stt.default_model == "stepaudio-2.5-asr"
    assert tts.default_model == "stepaudio-2.5-tts"
    assert "cixingnansheng" in tts.voices


def test_create_mock_stack():
    assert create_stt("mock").listen_once  # callable
    create_tts("mock").speak("hi")


def test_stt_list_has_cn_options():
    ids = {b.id for b in list_stt_backends()}
    assert {"mock", "whisper", "stepfun_plan", "stepfun"} <= ids
