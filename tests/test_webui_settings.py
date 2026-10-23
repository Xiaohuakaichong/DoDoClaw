"""Settings page: reminder defaults/budget, settings.yaml persistence, and the
.env key helpers (no key leakage, .env never written, no real network)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from dodoclaw.webui import keycheck, settings_store as st
from dodoclaw.webui.app import Bridge

SECRET = "sk-test-SHOULD-NEVER-LEAK-1234567890"


# ── reminder defaults (domain/reminder-budget.md) ───────
# Rows without an engine rule (神龛/魔方/肉山/不朽盾/TP) are off and not counted.
@pytest.mark.parametrize("pos,count", [([1], 3), ([2], 13), ([3], 3), ([4], 9), ([5], 9), ([1, 2, 3, 4, 5], 19)])
def test_budget_per_position(pos, count):
    assert st.budget(st.defaults(pos)["reminders"]) == count


def test_defaults_stay_under_cap():
    for pos in ([1], [2], [3], [4], [5], [1, 2, 3, 4, 5]):
        assert st.budget(st.defaults(pos)["reminders"]) <= st.BUDGET_CAP


def test_bounty_only_45_runes_only_2_lowhp_off():
    for p in (1, 2, 3, 4, 5):
        rem = st.defaults([p])["reminders"]
        assert rem["bounty"]["on"] is (p in (4, 5))
        assert rem["runes"]["on"] is (p == 2)
        assert rem["lowhp"]["on"] is False  # PRD 3.C1: off by default
        assert rem["buyback"]["on"] is True


def test_pending_rows_off_uncounted_and_locked():
    cur = st.defaults([2])
    for k in st.PENDING:
        assert cur["reminders"][k]["on"] is False
        new, err = st.toggle_reminder(cur, k, True)
        assert err == "这条提醒还在做" and new is cur
    forced = st.merge({"reminders": {k: {"on": True} for k in st.PENDING}, "overrides": list(st.PENDING)})
    assert all(forced["reminders"][k]["on"] is False for k in st.PENDING)
    assert forced["overrides"] == []
    on_all = {k: {"on": True} for k in st.REMINDERS}
    assert st.budget(on_all) == 6 + 10 + 3  # pending rows (and lowhp) never counted


def test_position_change_keeps_manual_overrides():
    cur = st.defaults([1])
    cur, err = st.toggle_reminder(cur, "buyback", False)
    assert not err
    cur = st.apply_positions(cur, [4])
    assert cur["reminders"]["bounty"]["on"] is True
    assert cur["reminders"]["buyback"]["on"] is False  # user's choice survives


def test_cap_warns_but_never_blocks(monkeypatch):
    monkeypatch.setattr(st, "BUDGET_CAP", 10)
    cur = st.defaults([2])  # 13 > 10
    cur, _ = st.toggle_reminder(cur, "runes", False)  # 3
    new, err = st.toggle_reminder(cur, "runes", True)
    assert err == "" and new["reminders"]["runes"]["on"] is True
    new, err = st.toggle_reminder(new, "bounty", True)
    assert err == "" and st.budget(new["reminders"]) == 19 > st.BUDGET_CAP
    assert "超过建议的 30 条" in st.OVER_CAP_HINT


def test_saved_lead_is_ignored():
    out = st.merge({"reminders": {"bounty": {"on": True, "lead": 45}}})
    assert out["reminders"]["bounty"]["lead"] == st.REMINDERS["bounty"][1]


def test_lead_is_clamped():
    assert st.clamp_lead(2) == 5 and st.clamp_lead(99) == 60 and st.clamp_lead(17) == 15


def test_save_only_touches_ui_block(tmp_path: Path):
    p = tmp_path / "settings.yaml"
    original = "# top comment\ngsi:\n  port: 3000  # keep me\n\nvoice:\n  stt_backend: \"mock\"\n"
    p.write_text(original, encoding="utf-8")
    s = st.defaults([2])
    st.save(p, s)
    st.save(p, st.apply_positions(s, [5]))
    text = p.read_text(encoding="utf-8")
    assert text.startswith(original.rstrip("\n"))
    assert "# keep me" in text and text.count("\nui:") == 1
    loaded = st.load(p)
    assert loaded["positions"] == [5] and loaded["reminders"]["bounty"]["on"] is True


def test_save_replaces_block_in_the_middle(tmp_path: Path):
    p = tmp_path / "settings.yaml"
    p.write_text("a: 1\nui:\n  positions: [1]\n\n# next\nlogging:\n  level: INFO\n", encoding="utf-8")
    st.save(p, st.defaults([3]))
    text = p.read_text(encoding="utf-8")
    assert "logging:\n  level: INFO" in text and "# next" in text and text.count("ui:") == 1
    assert st.load(p)["positions"] == [3]


# ── .env helpers ───────────────────────────────────────
@pytest.fixture
def envfile(tmp_path, monkeypatch):
    for k in keycheck.KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".env"
    p.write_text(f"LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY={SECRET}\n", encoding="utf-8")
    yield p
    for k in keycheck.KEY_ENVS:
        os.environ.pop(k, None)


def _fake_bridge(envfile: Path, provider="deepseek", provider_name="DeepSeek"):
    b = Bridge.__new__(Bridge)
    coach = SimpleNamespace(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")

    def reload_llm():
        coach.api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    b._svc = SimpleNamespace(provider_id=provider, provider_name=provider_name, coach=coach, reload_llm=reload_llm)
    b._env_path = envfile
    b._env_names = set()
    b._last_test = {}
    return b


def test_reload_env_returns_booleans_only_and_never_writes(envfile, caplog):
    caplog.set_level(logging.DEBUG)
    before = envfile.read_bytes(), envfile.stat().st_mtime_ns
    b = _fake_bridge(envfile)
    res = b.reload_env()
    dumped = json.dumps(res, ensure_ascii=False)
    assert SECRET not in dumped and SECRET not in caplog.text
    assert res["key"]["configured"] is True and res["key"]["key_env"] == "DEEPSEEK_API_KEY"
    assert res["keys"]["DEEPSEEK_API_KEY"] is True and res["keys"]["STEPFUN_API_KEY"] is False
    assert all(isinstance(v, bool) for v in res["keys"].values())
    assert (envfile.read_bytes(), envfile.stat().st_mtime_ns) == before


def test_reload_env_picks_up_removed_key(envfile):
    b = _fake_bridge(envfile)
    assert b.reload_env()["key"]["configured"] is True
    envfile.write_text("LLM_PROVIDER=deepseek\n", encoding="utf-8")  # user deletes the line
    res = b.reload_env()
    assert res["key"]["configured"] is False and res["keys"]["DEEPSEEK_API_KEY"] is False


def test_key_status_stt_flags():
    assert keycheck.key_status("deepseek", "DeepSeek", "")["has_stt"] is False
    s = keycheck.key_status("stepfun_plan", "阶跃", SECRET)
    assert s["has_stt"] is True and s["stepfun_key"] is True and SECRET not in json.dumps(s)


# ── test_key (network mocked) ──────────────────────────
class _Client:
    def __init__(self, exc=None, calls=None):
        self.exc, self.calls = exc, calls if calls is not None else []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[])


def _factory(exc=None, calls=None):
    return lambda **kw: _Client(exc, calls)


def _resp(code):
    return httpx.Response(code, request=httpx.Request("POST", "https://api.example.com/chat/completions"))


def test_test_key_ok_minimal_request():
    calls: list = []
    r = keycheck.test_key(
        SECRET, "https://api.example.com", "m", client_factory=_factory(calls=calls),
        extra_body={"thinking": {"type": "disabled"}},
    )
    assert r["ok"] is True and r["reason_zh"] == "连接正常"
    assert calls[0]["max_tokens"] <= 8 and len(calls[0]["messages"]) == 1
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize(
    "exc,reason",
    [
        (openai.AuthenticationError(f"Incorrect API key provided: {SECRET}", response=_resp(401), body=None), "Key 无效"),
        (openai.RateLimitError("quota", response=_resp(429), body=None), "请求太频繁"),
        (openai.APIStatusError("pay", response=_resp(402), body=None), "账户余额不足"),
        (openai.NotFoundError("no model", response=_resp(404), body=None), "模型名"),
        (openai.APITimeoutError(request=httpx.Request("POST", "https://x")), "联网失败"),
        (openai.APIConnectionError(request=httpx.Request("POST", "https://x")), "联网失败"),
        (RuntimeError(f"boom {SECRET}"), "教练服务出错"),
    ],
)
def test_test_key_errors_are_chinese_and_leak_nothing(exc, reason, caplog):
    caplog.set_level(logging.DEBUG)
    r = keycheck.test_key(SECRET, "https://api.example.com", "m", client_factory=_factory(exc))
    assert r["ok"] is False and reason in r["reason_zh"]
    assert SECRET not in json.dumps(r, ensure_ascii=False) and SECRET not in caplog.text


def test_test_key_without_key_makes_no_request():
    calls: list = []
    r = keycheck.test_key("", "https://api.example.com", "m", client_factory=_factory(calls=calls))
    assert r == {"ok": False, "kind": "no_key", "reason_zh": "还没填 Key", "ms": None} and calls == []


def test_bridge_test_key_uses_mocked_client(envfile, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    seen = {}

    def fake_openai(**kw):
        seen.update(kw)
        return _Client(openai.AuthenticationError(f"bad {SECRET}", response=_resp(401), body=None))

    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    before = envfile.read_bytes()
    b = _fake_bridge(envfile)
    b.reload_env()
    r = b.test_key()
    assert seen["api_key"] == SECRET and seen["max_retries"] == 0  # went to the (fake) client only
    assert r == {"ok": False, "kind": "auth", "reason_zh": "Key 无效或已过期", "ms": None}
    assert b._coach_err["reason_zh"] == "Key 无效或已过期"  # the home card shows it too
    assert SECRET not in json.dumps(b._last_test) and SECRET not in caplog.text
    assert envfile.read_bytes() == before


def _bridge_for_save(tmp_path):
    b = Bridge.__new__(Bridge)
    b.ui = st.defaults([2])
    b._ui_path = tmp_path / "settings.yaml"
    b._ui_path.write_text("# keep\n", encoding="utf-8")
    return b


def test_bridge_save_ignores_lead_and_refuses_pending(tmp_path):
    b = _bridge_for_save(tmp_path)
    r = b.save_settings({"reminder": "bounty", "lead": 45})
    assert r["ok"] and b.ui["reminders"]["bounty"]["lead"] == 15
    assert st.load(b._ui_path)["reminders"]["bounty"]["lead"] == 15
    r = b.save_settings({"reminder": "roshan", "on": True})
    assert r == {"ok": False, "msg": "这条提醒还在做"} and b.ui["reminders"]["roshan"]["on"] is False
    r = b.save_settings({"positions": [1, 2, 3, 4, 5]})
    assert r["ok"]


def test_bridge_test_key_sends_thinking_off_for_deepseek(envfile, monkeypatch):
    seen = {}

    class C(_Client):
        def _create(self, **kw):
            seen.update(kw)
            return SimpleNamespace(choices=[])

    monkeypatch.setattr(openai, "OpenAI", lambda **kw: C())
    b = _fake_bridge(envfile)
    b._svc.coach.model = "deepseek-flash"
    b.reload_env()
    assert b.test_key()["ok"] is True
    assert seen["extra_body"] == {"thinking": {"type": "disabled"}} and seen["model"] == "deepseek-flash"
