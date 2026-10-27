"""Provider defaults must reach Chat Completions with compatible parameters."""

from types import SimpleNamespace

import pytest

from dodoclaw.coach.agent import CoachAgent
from dodoclaw.providers import get_provider


@pytest.mark.parametrize(
    "provider,temperature,tokens,body",
    [
        ("moonshot", 1.0, 8192, {"reasoning_effort": "low"}),
        ("zhipu", 0.55, 8192, {"reasoning_effort": "low"}),
        ("minimax", 0.55, 500, {"thinking": {"type": "disabled"}}),
        ("deepseek", 0.55, 500, {"thinking": {"type": "disabled"}}),
    ],
)
def test_default_coach_request_parameters(provider, temperature, tokens, body):
    spec = get_provider(provider)
    coach = CoachAgent("fake-key", spec.base_url, spec.default_model, provider_id=provider)
    sent = {}

    def create(**request):
        sent.update(request)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="先补好视野"))])

    coach._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    snapshot = SimpleNamespace(summary_for_llm=lambda: "游戏时间 10:00")
    assert coach.answer("现在该做什么", snapshot) == "先补好视野"
    assert sent["model"] == spec.default_model
    assert (sent["temperature"], sent["max_tokens"], sent["extra_body"]) == (
        temperature, tokens, body,
    )
