"""PRD D10 (design/v2 README): 服务商 dropdown, in-app key entry behind the
KeyStore interface (.env backend only), save-then-test, per-provider keys,
STT defaults that follow the provider, and the 缺少声音组件 state.

Everything runs in tmp dirs with monkeypatched paths; no real .env / settings.yaml
is read or written and no network request is made."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import openai
import pytest
from dotenv import dotenv_values

from dodoclaw import config, service
from dodoclaw.coach.agent import CoachAgent
from dodoclaw.config import Settings
from dodoclaw.service import DoDoClawService
from dodoclaw.webui import keycheck, keystore, tts_preview
from dodoclaw.webui import settings_store as st
from dodoclaw.webui.app import Bridge

SECRET = "sk-picker-NEVER-LEAK-9f8e7d6c5bQzX9"
OLD = "sk-old-step-key-AAAA1111"

YAML = """# DoDoClaw settings — keep this comment
gsi:
  port: 3000

coach:
  language: "zh-CN"
  # provider comment stays
  provider: "stepfun_plan"
  model: "step-3.5-flash"
  max_reply_chars: 400

ui:
  positions: [1]
"""


# ── .env writer ──────────────────────────────────────────
def test_env_writer_creates_missing_file_utf8_no_bom(tmp_path):
    p = tmp_path / "sub" / ".env"
    keystore.upsert_env_line(p, "DEEPSEEK_API_KEY", SECRET)
    raw = p.read_bytes()
    assert raw == f"DEEPSEEK_API_KEY={SECRET}\n".encode()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_env_writer_replaces_in_place_and_keeps_everything_else(tmp_path):
    p = tmp_path / ".env"
    before = (
        "# 教练 Key\n"
        "LLM_API_KEY=\n"
        "\n"
        "# DEEPSEEK_API_KEY=commented-example\n"
        "STEPFUN_API_KEY=" + OLD + "\n"
        "DEEPSEEK_API_KEY=old-value   \n"
        "GSI_PORT=3000\n"
        "export DEEPSEEK_API_KEY=dup\n"
        "# 结尾注释"  # no trailing newline
    )
    p.write_text(before, encoding="utf-8")
    keystore.upsert_env_line(p, "DEEPSEEK_API_KEY", SECRET)
    after = p.read_text(encoding="utf-8")
    exp = before.replace("DEEPSEEK_API_KEY=old-value   ", f"DEEPSEEK_API_KEY={SECRET}").replace(
        "export DEEPSEEK_API_KEY=dup", f"DEEPSEEK_API_KEY={SECRET}"
    )
    assert after == exp  # only the active lines changed; the commented example and order are untouched
    vals = dotenv_values(p)
    assert vals["DEEPSEEK_API_KEY"] == SECRET and vals["STEPFUN_API_KEY"] == OLD and vals["GSI_PORT"] == "3000"


def test_env_writer_appends_when_missing_and_keeps_crlf(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes(b"\xef\xbb\xbf# win\r\nSTEPFUN_API_KEY=" + OLD.encode() + b"\r\nGSI_PORT=3000")
    keystore.upsert_env_line(p, "XAI_API_KEY", SECRET)
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")  # BOM dropped, nothing else
    assert raw == b"# win\r\nSTEPFUN_API_KEY=" + OLD.encode() + b"\r\nGSI_PORT=3000\r\nXAI_API_KEY=" + SECRET.encode() + b"\r\n"


def test_env_writer_backs_up_old_file_first(tmp_path):
    p = tmp_path / ".env"
    p.write_bytes(b"# mine\nDEEPSEEK_API_KEY=old\n")
    keystore.upsert_env_line(p, "DEEPSEEK_API_KEY", SECRET)
    assert (tmp_path / ".env.bak").read_bytes() == b"# mine\nDEEPSEEK_API_KEY=old\n"
    assert not (tmp_path / ".env.tmp").exists()


def test_env_writer_new_file_has_no_backup(tmp_path):
    keystore.upsert_env_line(tmp_path / ".env", "DEEPSEEK_API_KEY", SECRET)
    assert not (tmp_path / ".env.bak").exists()


@pytest.mark.parametrize("val", ["abc#def", "a$b{c}"])
def test_env_writer_quotes_values_dotenv_would_mangle(tmp_path, val):
    p = tmp_path / ".env"
    keystore.upsert_env_line(p, "OPENAI_API_KEY", val)
    assert dotenv_values(p)["OPENAI_API_KEY"] == val


@pytest.mark.parametrize(
    "val,reason",
    [
        ("", keystore.MSG_EMPTY),
        ("   \t ", keystore.MSG_EMPTY),
        ("sk-a\nOTHER=1", keystore.MSG_NEWLINE),
        ("sk-a\rb", keystore.MSG_NEWLINE),
        ("sk a", keystore.MSG_BAD_CHARS),
        ('sk"a', keystore.MSG_BAD_CHARS),
        ("sk-中文", keystore.MSG_BAD_CHARS),
    ],
)
def test_save_key_rejects_bad_values(tmp_path, monkeypatch, val, reason):
    p = tmp_path / ".env"
    p.write_text("KEEP=1\n", encoding="utf-8")
    monkeypatch.setattr(keystore, "_store", keystore.EnvFileKeyStore(p))
    with pytest.raises(keystore.KeyStoreError) as ei:
        keystore.save_key("DEEPSEEK_API_KEY", val)
    assert ei.value.reason_zh == reason
    assert p.read_text(encoding="utf-8") == "KEEP=1\n"


def test_save_key_trims_and_only_writes_key_variables(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    monkeypatch.setattr(keystore, "_store", keystore.EnvFileKeyStore(p))
    keystore.save_key("DEEPSEEK_API_KEY", f"  {SECRET}\n")  # trailing newline from a paste is trimmed
    assert dotenv_values(p)["DEEPSEEK_API_KEY"] == SECRET
    with pytest.raises(keystore.KeyStoreError):
        keystore.save_key("GSI_AUTH_TOKEN", "x")
    for spec_env in ("STEPFUN_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        assert spec_env in keystore.ALLOWED_VARS


def test_write_error_message_has_no_key(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    d = tmp_path / "is_a_dir"
    d.mkdir()
    monkeypatch.setattr(keystore, "_store", keystore.EnvFileKeyStore(d))
    with pytest.raises(keystore.KeyStoreError) as ei:
        keystore.save_key("DEEPSEEK_API_KEY", SECRET)
    assert ei.value.reason_zh == keystore.MSG_WRITE and ei.value.__cause__ is None
    assert SECRET not in str(ei.value) and SECRET not in caplog.text


# ── KeyStore interface ───────────────────────────────────
def test_keystore_is_one_swappable_interface(monkeypatch):
    calls = []

    class Fake:  # e.g. a future 凭据管理器 backend: get / set / has / delete
        def get(self, env_var):
            return ""

        def set(self, env_var, value):
            calls.append((env_var, value))

        def has(self, env_var):
            return env_var == "XAI_API_KEY"

        def delete(self, env_var):
            calls.append((env_var, None))

    monkeypatch.setattr(keystore, "_store", Fake())
    keystore.save_key("XAI_API_KEY", f" {SECRET} ")
    assert calls == [("XAI_API_KEY", SECRET)]
    assert keystore.has_key("XAI_API_KEY") and not keystore.has_key("OPENAI_API_KEY")
    assert keystore.store() is keystore._store


def test_env_store_get_set_has_delete(tmp_path, monkeypatch):
    for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".env"
    p.write_text(f"# c\nDEEPSEEK_API_KEY={SECRET}\nOPENAI_API_KEY=\nGSI_PORT=3000\n", encoding="utf-8")
    ks = keystore.EnvFileKeyStore(p)
    assert ks.has("DEEPSEEK_API_KEY") is True and ks.has("OPENAI_API_KEY") is False
    assert ks.get("DEEPSEEK_API_KEY") == SECRET  # Python-side only; the bridge never returns it
    monkeypatch.setenv("OPENAI_API_KEY", "x")  # a system env var counts too
    assert ks.has("OPENAI_API_KEY") is True
    ks.set("OPENAI_API_KEY", "sk-new")
    assert dotenv_values(p)["OPENAI_API_KEY"] == "sk-new"
    ks.delete("DEEPSEEK_API_KEY")
    assert p.read_text(encoding="utf-8") == "# c\nOPENAI_API_KEY=sk-new\nGSI_PORT=3000\n"
    assert ks.has("DEEPSEEK_API_KEY") is False


def test_no_credential_manager_dependency():
    src = (Path(keystore.__file__)).read_text(encoding="utf-8")
    assert "import keyring" not in src and "win32cred" not in src and "CredWrite" not in src


def test_hand_written_env_keys_still_resolve(tmp_path, monkeypatch):
    """Reading is unchanged: a key typed into .env by hand is used as before."""
    for k in keycheck.KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "settings.yaml"
    cfg.write_text('coach:\n  provider: "stepfun_plan"\n', encoding="utf-8")
    monkeypatch.setattr(Settings, "yaml_path", lambda self: cfg)
    env = tmp_path / ".env"
    env.write_text(f"STEPFUN_API_KEY={OLD}\n", encoding="utf-8")
    assert Settings(_env_file=str(env)).resolve_llm()[2] == OLD


# ── provider list / links ────────────────────────────────
def test_picker_is_exactly_the_five_d10_providers():
    rows = keycheck.list_providers("deepseek")
    assert [r["id"] for r in rows] == ["deepseek", "stepfun_plan", "stepfun", "xai", "openai"]
    by = {r["id"]: r for r in rows}
    assert by["deepseek"]["tag"] == "默认 · 推荐" and by["deepseek"]["current"]
    assert by["xai"]["tag"] == "国内需代理" and "SuperGrok 会员不含 API 额度" in by["xai"]["hint"]
    assert by["openai"]["tag"] == "国内需代理" and "ChatGPT Plus 不含 API 额度" in by["openai"]["hint"]
    # Step Plan and 按量 share STEPFUN_API_KEY
    assert by["stepfun_plan"]["shares_key_with"] == ["stepfun"] and by["stepfun"]["shares_key_with"] == ["stepfun_plan"]
    assert all(r["apply_url"].startswith("https://") for r in rows)
    assert all("_" not in r["name"] for r in rows)  # display names only, no internal ids
    assert set(rows[0]) == {"id", "name", "tag", "model", "configured", "shares_key_with", "hint", "apply_url", "current"}


def test_apply_links_go_to_key_pages():
    from dodoclaw.providers import get_provider

    assert get_provider("deepseek").apply_url() == "https://platform.deepseek.com/api_keys"
    assert get_provider("openai").apply_url() == "https://platform.openai.com/api-keys"
    assert get_provider("xai").apply_url() == "https://console.x.ai"
    assert get_provider("stepfun_plan").apply_url() == "https://platform.stepfun.com/interface-key"
    assert get_provider("stepfun").apply_url() == "https://platform.stepfun.com/interface-key"
    assert get_provider("stepfun_plan").topup_url() == "https://platform.stepfun.com/step-plan"
    assert get_provider("deepseek").topup_url() == "https://platform.deepseek.com/top_up"
    assert get_provider("xai").topup_url() == "https://console.x.ai"  # no billing page known: key page
    assert get_provider("moonshot").apply_url() == get_provider("moonshot").docs_url  # no key_url: docs


def test_open_key_page_uses_provider_and_purpose(world, monkeypatch):
    import webbrowser

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u) or True)
    b = world.b
    assert b.open_key_page("xai") and b.open_key_page("stepfun_plan", "topup") and b.open_key_page()
    assert opened == ["https://console.x.ai", "https://platform.stepfun.com/step-plan", "https://platform.stepfun.com/interface-key"]


def test_failure_guides_are_fixed_chinese():
    g = keycheck.test_guide("plan_expired")
    assert g["link"] == "topup" and g["link_zh"] == "去续订" and "阶跃按量" in g["detail_zh"]
    assert g["detail_zh"].endswith("提醒不受影响。")
    assert keycheck.test_guide("auth")["link"] == "key" and keycheck.test_guide("balance")["link_zh"] == "去充值"
    assert keycheck.test_guide("network")["link"] == "" and keycheck.test_guide("weird")["link"] == "log"


# ── bridge with a real settings.yaml in tmp ──────────────
@pytest.fixture
def world(tmp_path, monkeypatch):
    for k in keycheck.KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    cfgdir = tmp_path / "config"
    cfgdir.mkdir()
    (cfgdir / "settings.yaml").write_text(YAML, encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text(f"# 我的 Key\nSTEPFUN_API_KEY={OLD}\nGSI_PORT=3000\n", encoding="utf-8")

    monkeypatch.setattr(config, "config_dir", lambda: cfgdir)
    fresh = lambda: Settings(_env_file=str(env))
    monkeypatch.setattr(config, "reload_settings", fresh)
    monkeypatch.setattr(service, "reload_settings", fresh)
    monkeypatch.setattr(keystore, "_store", keystore.EnvFileKeyStore(env))
    monkeypatch.setattr(keystore, "env_path", lambda: env)

    svc = DoDoClawService.__new__(DoDoClawService)
    svc.on_log = lambda *_a: None
    svc.settings = fresh()
    pid, pname, key, url, model = svc.settings.resolve_llm()
    svc.provider_id, svc.provider_name = pid, pname
    svc.coach = CoachAgent(api_key=key, base_url=url, model=model, provider_id=pid, provider_name=pname)
    svc.stt_backend, svc.tts_backend, svc.tts_voice = "mock", "edge", ""
    svc.voice_calls = []
    svc.reload_voice = lambda **kw: (svc.voice_calls.append(kw), setattr(svc, "stt_backend", kw.get("stt_backend", svc.stt_backend)))

    b = Bridge.__new__(Bridge)
    b._svc = svc
    b._env_path = env
    b._env_names = keycheck.env_names_in_file(env)
    b._ui_path = cfgdir / "settings.yaml"
    b.ui = st.load(b._ui_path)
    b._last_test, b._coach_err = {}, {}
    b._icons = SimpleNamespace(root=tmp_path / "icons")
    svc.snapshot = lambda: SimpleNamespace(updated_at=None)
    svc.gsi = SimpleNamespace(host="127.0.0.1", port=3000, auth_token="t")
    svc.store, svc._recorder = SimpleNamespace(update_count=0), None
    monkeypatch.setattr("dodoclaw.gsi_install.resolve_dota_cfg_target", lambda: None)
    yield SimpleNamespace(b=b, svc=svc, env=env, yaml=cfgdir / "settings.yaml")
    for k in keycheck.KEY_ENVS:
        os.environ.pop(k, None)


def test_switch_provider_persists_and_reload_picks_it_up(world):
    b, svc = world.b, world.svc
    assert svc.provider_id == "stepfun_plan" and svc.coach.model == "step-3.5-flash"
    assert b.reload_env()["key"]["configured"] is True
    r = b.set_provider("deepseek")
    assert r["ok"] and r["msg"] == "" and r["provider"] == "deepseek" and r["model"] == "deepseek-flash"
    text = world.yaml.read_text(encoding="utf-8")
    # coach.provider + coach.model (that provider's default) written; everything else kept
    assert 'provider: "deepseek"' in text and 'model: "deepseek-flash"' in text and "step-3.5-flash" not in text
    assert "# DoDoClaw settings — keep this comment" in text and "# provider comment stays" in text
    assert "max_reply_chars: 400" in text and "positions:" in text
    # live coach client, no restart
    assert (svc.provider_id, svc.coach.model, svc.coach.base_url) == ("deepseek", "deepseek-flash", "https://api.deepseek.com")
    # each provider keeps its own key: StepFun's is not carried over to DeepSeek
    assert svc.coach.api_key == "" and r["key"] == {"configured": False}
    # the page offers “切回 阶跃 Step Plan” because that key is still there
    k = b.settings_state()["key"]
    assert k["configured"] is False and k["switched_from"] == {"id": "stepfun_plan", "name": "阶跃 Step Plan"}
    assert k["provider_name"] == "DeepSeek" and k["key_env"] == "DEEPSEEK_API_KEY" and "source" not in k
    # and back: StepFun's key is still there
    assert b.set_provider("stepfun_plan")["key"]["configured"] is True
    assert svc.coach.api_key == OLD and svc.coach.model == "step-3.7-flash"
    assert b.settings_state()["key"]["switched_from"] is None


def test_step_plan_and_pay_as_you_go_share_one_key(world):
    b = world.b
    b.reload_env()
    rows = {r["id"]: r for r in b.list_providers()}
    assert rows["stepfun_plan"]["configured"] and rows["stepfun"]["configured"]
    assert not rows["deepseek"]["configured"] and not rows["xai"]["configured"]
    assert b.set_provider("stepfun")["key"]["configured"] is True
    assert b.settings_state()["key"]["key_env"] == "STEPFUN_API_KEY"


def test_switch_rejects_unknown_provider_and_keeps_yaml(world):
    before = world.yaml.read_bytes()
    for bad in ("evil; rm -rf", "moonshot", "custom"):  # other presets live in settings.yaml, not this dropdown
        r = world.b.set_provider(bad)
        assert r["ok"] is False and r["msg"] == "没有这个服务商"
    assert world.yaml.read_bytes() == before


class _Client:
    def __init__(self, seen, exc=None):
        self.seen, self.exc = seen, exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.seen.append(kw)
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[])


def test_bridge_save_key_stores_reloads_and_auto_tests(world, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    b, svc = world.b, world.svc
    b.set_provider("deepseek")
    seen, made = [], []

    def fake_openai(**kw):
        made.append(kw)
        return _Client(seen)

    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    r = b.save_key("deepseek", f"  {SECRET}  ")
    assert r["ok"] is True and r["kind"] == "ok" and r["configured"] is True and r["model"] == "deepseek-flash"
    assert set(r) == {"ok", "kind", "reason_zh", "ms", "model", "configured", "saved", "msg"}
    # written next to the exe, other lines untouched, old file backed up
    assert world.env.read_text(encoding="utf-8") == (
        f"# 我的 Key\nSTEPFUN_API_KEY={OLD}\nGSI_PORT=3000\nDEEPSEEK_API_KEY={SECRET}\n"
    )
    assert (world.env.parent / ".env.bak").read_text(encoding="utf-8") == f"# 我的 Key\nSTEPFUN_API_KEY={OLD}\nGSI_PORT=3000\n"
    # reloaded into the live coach and tested once with the new key
    assert svc.coach.api_key == SECRET
    assert len(made) == 1 and made[0]["api_key"] == SECRET and made[0]["base_url"] == "https://api.deepseek.com"
    assert made[0]["timeout"] == 15.0 and seen[0]["model"] == "deepseek-flash"
    assert b.settings_state()["key"]["last_test"]["ok"] is True  # shows in 测试结果
    dumped = json.dumps(r, ensure_ascii=False) + json.dumps(b.settings_state(), ensure_ascii=False)
    dumped += json.dumps(b.list_providers(), ensure_ascii=False)
    assert SECRET not in dumped and "QzX9" not in dumped and SECRET not in caplog.text


def test_failed_test_keeps_the_key(world, monkeypatch):
    import httpx

    b, svc = world.b, world.svc
    b.set_provider("deepseek")
    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    exc = openai.AuthenticationError(f"bad key {SECRET}", response=httpx.Response(401, request=req), body=None)
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _Client([], exc))
    r = b.save_key("deepseek", SECRET)
    assert r["ok"] is False and r["kind"] == "auth" and r["reason_zh"] == "Key 无效或已过期"
    assert r["configured"] is True and r["saved"] is True  # save first, then test: the key stays
    assert dotenv_values(world.env)["DEEPSEEK_API_KEY"] == SECRET and svc.coach.api_key == SECRET
    t = b.settings_state()["key"]["last_test"]
    assert t["kind"] == "auth" and t["link"] == "key" and "更换 Key" in t["detail_zh"]
    assert SECRET not in json.dumps(r, ensure_ascii=False) and SECRET not in json.dumps(b.settings_state(), ensure_ascii=False)


def test_plan_expired_offers_renew(world, monkeypatch):
    import httpx

    b = world.b
    b.reload_env()
    req = httpx.Request("POST", "https://api.stepfun.com/step_plan/v1/chat/completions")
    exc = openai.PermissionDeniedError(
        "no active step plan subscription", response=httpx.Response(403, request=req), body=None
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: _Client([], exc))
    r = b.save_key("stepfun_plan", OLD)
    assert r["kind"] == "plan_expired" and r["configured"] is True
    t = b.settings_state()["key"]["last_test"]
    assert t["link"] == "topup" and t["link_zh"] == "去续订"


def test_bridge_save_key_rejected_value_no_write_no_test(world, monkeypatch):
    b = world.b
    before = world.env.read_bytes()
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: pytest.fail("no request for a rejected key"))
    r = b.save_key("stepfun_plan", "sk-a\nGSI_PORT=1")
    assert r["ok"] is False and r["kind"] == "invalid" and r["reason_zh"] == keystore.MSG_NEWLINE and r["saved"] is False
    assert world.env.read_bytes() == before
    assert b.save_key("stepfun_plan", None)["reason_zh"] == keystore.MSG_EMPTY
    # a key typed for another provider is never filed under the current one
    r = b.save_key("xai", SECRET)
    assert r["ok"] is False and r["saved"] is False and world.env.read_bytes() == before


def test_settings_state_never_contains_key_material(world):
    b = world.b
    b.reload_env()
    s = b.settings_state()
    dumped = json.dumps(s, ensure_ascii=False)
    assert OLD not in dumped and "AAAA1111" not in dumped
    assert s["key"]["configured"] is True and s["key"]["provider_name"] == "阶跃 Step Plan"
    assert "source" not in s["key"]  # storage location is not exposed
    key_vals = [v for k, v in s["key"].items() if not isinstance(v, (bool, dict)) and v is not None]
    assert all(isinstance(v, str) and len(v) < 60 for v in key_vals)
    assert all(isinstance(r["configured"], bool) for r in s["providers"])


# ── voice follows the provider ───────────────────────────
def test_stt_default_follows_provider_but_not_user_choice(world, monkeypatch):
    b = world.b
    b.reload_env()
    assert b.settings_state()["voice"]["stt_default"] == "cloud"  # StepFun shares its key
    b.set_provider("deepseek")
    v = b.settings_state()["voice"]
    assert v["stt_default"] == "local" and v["stt_mode"] == "local"
    # a mode the user picked by hand survives a switch
    b.ui["stt_mode"] = "cloud"
    b.set_provider("stepfun_plan")
    b.set_provider("openai")
    assert b.ui["stt_mode"] == "cloud" and b.settings_state()["voice"]["stt_mode"] == "cloud"


def test_voice_on_following_provider_is_reapplied(world, monkeypatch):
    b, svc = world.b, world.svc
    b.reload_env()
    b.ui["voice_ask"], b.ui["stt_mode"] = True, None
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: object())
    b.set_provider("stepfun")
    assert svc.voice_calls[-1] == {"stt_backend": "stepfun"}
    b.set_provider("deepseek")
    assert svc.voice_calls[-1] == {"stt_backend": "whisper"}


# ── 缺少声音组件 (README D10 #coach,tts-missing) ──────────
def _find_spec(missing: bool):
    import importlib.util

    real = importlib.util.find_spec
    return lambda name, *a: None if (name == "edge_tts" and missing) else (object() if name == "edge_tts" else real(name, *a))


def test_voice_state_flags_missing_tts(world, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _find_spec(True))
    v = world.b.settings_state()["voice"]
    assert v["tts_available"] is False and v["tts_missing_zh"] == "缺少声音组件"
    assert v["tts_missing_detail_zh"] == "没打包 Edge TTS"
    assert world.b.set_tts(True)["ok"] is False  # switch is disabled too


def test_voice_state_tts_available_when_found(world, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _find_spec(False))
    assert world.b.settings_state()["voice"]["tts_available"] is True


def test_tts_available_uses_find_spec(monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", _find_spec(True))
    assert tts_preview.tts_available() is False
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: (_ for _ in ()).throw(ValueError("x")))
    assert tts_preview.tts_available() is False
