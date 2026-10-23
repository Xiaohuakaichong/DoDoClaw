"""PRD D9: provider failures become a short Chinese reason + settings link; the
web UI state exposes only {kind, reason_zh}. No key material anywhere."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import openai
import pytest

from dodoclaw.coach.errors import classify
from dodoclaw.webui.app import Bridge

SECRET = "sk-test-SHOULD-NEVER-LEAK-1234567890"
STEP_BODY = '{"error":{"message":"you have no active step plan subscription","type":"invalid_request_error"}}'


def _status_err(code: int, text: str = "", cls=openai.APIStatusError):
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    resp = httpx.Response(code, request=req, content=text.encode("utf-8"))
    body = json.loads(text)["error"] if text.startswith("{") else None
    return cls(f"Error code: {code} - {text} {SECRET}", response=resp, body=body)


@pytest.mark.parametrize("code", [400, 403])
def test_stepfun_plan_expired_exact_body(code):
    r = classify(_status_err(code, STEP_BODY))
    assert r == {"kind": "plan_expired", "reason_zh": "阶跃 Step Plan 订阅已失效", "href": "settings.html#coach"}


@pytest.mark.parametrize(
    "exc,kind,reason",
    [
        (_status_err(401, '{"error":{"message":"Incorrect API key"}}', openai.AuthenticationError), "auth", "Key 无效或已过期"),
        (_status_err(400, '{"error":{"message":"invalid api key"}}'), "auth", "Key 无效或已过期"),
        (_status_err(402, '{"error":{"message":"Insufficient Balance"}}'), "balance", "账户余额不足"),
        (_status_err(400, '{"error":{"message":"账户余额不足"}}'), "balance", "账户余额不足"),
        (_status_err(429, "", openai.RateLimitError), "rate_limit", "请求太频繁，稍后再试"),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://x")), "network", "联网失败，检查网络"),
        (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "network", "联网失败，检查网络"),
        (httpx.ConnectTimeout("t"), "network", "联网失败，检查网络"),
        (_status_err(500, "oops"), "http", "教练服务出错（HTTP 500）"),
        (_status_err(503), "http", "教练服务出错（HTTP 503）"),
        (ValueError(f"weird {SECRET}"), "unknown", "教练服务出错，详情见日志"),
    ],
)
def test_classifier_cases(exc, kind, reason):
    r = classify(exc)
    assert (r["kind"], r["reason_zh"]) == (kind, reason)
    assert SECRET not in json.dumps(r, ensure_ascii=False)


def test_wrapped_coach_error_reports_original_reason():
    """CoachAgent wraps the fallback failure in RuntimeError; the chat 400 is the real cause."""
    try:
        try:
            raise _status_err(400, STEP_BODY)
        except Exception:
            try:
                raise _status_err(404, "not found")  # responses API fallback
            except Exception as exc2:
                raise RuntimeError(f"LLM 调用失败: {exc2}") from exc2
    except RuntimeError as wrapped:
        assert classify(wrapped)["reason_zh"] == "阶跃 Step Plan 订阅已失效"


# ── Bridge: state exposes the last coach error ─────────
def _bridge(ask_exc=None):
    b = Bridge.__new__(Bridge)
    coach = SimpleNamespace(api_key=SECRET, base_url="https://api.stepfun.com/step_plan/v1", model="step-3.7-flash")
    snap = SimpleNamespace(clock_mmss="0:00")

    def ask(text, speak=False, raise_errors=False):
        assert raise_errors is True
        if b._next_exc:
            raise b._next_exc
        return "好的"

    b._svc = SimpleNamespace(coach=coach, ask=ask, snapshot=lambda: snap, provider_id="stepfun_plan")
    b._next_exc = ask_exc
    b._busy, b._error, b._answer, b._coach_err = False, "", {}, {}
    b._speaker = SimpleNamespace(say=lambda *_a, **_k: None)
    return b


def _run_ask(b, monkeypatch):
    import threading

    class Now:
        def __init__(self, target, **_kw):
            self.t = target

        def start(self):
            self.t()

    monkeypatch.setattr(threading, "Thread", Now)
    assert b.ask("现在出什么", voice=False)


def test_failed_answer_sets_reason_and_success_clears(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    b = _bridge(_status_err(400, STEP_BODY))
    _run_ask(b, monkeypatch)
    assert b._error == "阶跃 Step Plan 订阅已失效"
    assert b._coach_err["kind"] == "plan_expired"
    assert SECRET not in caplog.text and SECRET not in b._error
    b._next_exc = None
    _run_ask(b, monkeypatch)
    assert b._coach_err == {} and b._error == "" and b._answer["text"] == "好的"


def test_state_exposes_only_kind_and_reason(monkeypatch):
    b = _bridge(_status_err(400, STEP_BODY))
    _run_ask(b, monkeypatch)
    snap = SimpleNamespace(
        raw={}, updated_at=None, in_game=False, game_state="", clock_time=0, clock_mmss="0:00",
        hero_name="", hero_level=0, hero_alive=True, kills=0, deaths=0, assists=0, last_hits=0,
        denies=0, gold=0, gpm=0, items=[],
    )
    b._svc.snapshot = lambda: snap
    b._svc.gsi_update_count = 0
    b._svc.gsi = SimpleNamespace(host="127.0.0.1", port=3000)
    b._svc.provider_name = "阶跃星辰 Step Plan"
    b._svc.tts_backend = b._svc.stt_backend = "mock"
    b._timers = SimpleNamespace(ingest=lambda raw: None, compute=lambda c: [])
    b._speaker.speaking = False
    b._alert, b.compact, b.reduce_motion, b.ui = {}, False, False, {"overlay_opacity": 90}
    s = b.state()
    assert s["coach"]["error"] == {"kind": "plan_expired", "reason_zh": "阶跃 Step Plan 订阅已失效"}
    assert s["error"] == "阶跃 Step Plan 订阅已失效"
    assert SECRET not in json.dumps(s, ensure_ascii=False)
    b._svc.coach.api_key = ""  # no key: the card says "没有 Key" instead
    assert b.state()["coach"]["error"] is None


def test_settings_test_result_feeds_the_home_card(monkeypatch):
    from dodoclaw.webui import keycheck

    b = _bridge()
    b._svc.provider_id = "stepfun_plan"
    results = iter([
        {"ok": False, "kind": "plan_expired", "reason_zh": "阶跃 Step Plan 订阅已失效", "ms": None},
        {"ok": True, "kind": "ok", "reason_zh": "连接正常", "ms": 120},
    ])
    monkeypatch.setattr(keycheck, "test_key", lambda *a, **k: next(results))
    assert b.test_key()["ok"] is False and b._coach_err["reason_zh"] == "阶跃 Step Plan 订阅已失效"
    assert b._last_test["reason_zh"] == "阶跃 Step Plan 订阅已失效"  # 上次测试 row
    assert b.test_key()["ok"] is True and b._coach_err == {}
