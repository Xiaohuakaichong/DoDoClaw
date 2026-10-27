"""Provider Hub persistence and probes: temporary files, no remote calls."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest
import yaml
from dotenv import dotenv_values

from dodoclaw import config
from dodoclaw.config import Settings
from dodoclaw.webui import customs, keycheck, keystore, provider_store
from dodoclaw.webui.app import Bridge

SECRET = "sk-hub-NEVER-RETURN-782458"


@pytest.fixture
def hub(tmp_path, monkeypatch):
    for var in list(os.environ):
        if var in keycheck.KEY_ENVS or customs.is_custom_key_env(var):
            monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    path = tmp_path / "settings.yaml"
    path.write_text(
        '# keep me\ncoach:\n  provider: deepseek\n  model: legacy-model\n'
        '  base_url: https://legacy.example/v1\n  language: zh-CN\n'
        'voice:\n  tts_backend: edge\n', encoding="utf-8",
    )
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(customs, "_settings_path", lambda: path)
    monkeypatch.setattr(config, "reload_settings", lambda: None)
    monkeypatch.setattr(keystore, "_store", keystore.EnvFileKeyStore(env))
    b = Bridge.__new__(Bridge)
    svc = SimpleNamespace()

    def reload_llm():
        settings = Settings(_env_file=str(env))
        pid, name, key, url, model = settings.resolve_llm()
        svc.provider_id, svc.provider_name = pid, name
        svc.coach = SimpleNamespace(api_key=key, base_url=url, model=model)

    svc.reload_llm = reload_llm
    reload_llm()
    b._svc, b._env_path, b._env_names = svc, env, set()
    b._last_test, b._coach_err = {}, {}
    b._follow_provider_stt = lambda: ""
    b._save_ui = lambda: None
    monkeypatch.setattr(keycheck, "test_key", lambda *a, **kw: pytest.fail("unexpected network probe"))
    yield SimpleNamespace(b=b, svc=svc, path=path, env=env)
    for var in list(os.environ):
        if var in keycheck.KEY_ENVS or customs.is_custom_key_env(var):
            os.environ.pop(var, None)


def _row(hub, pid):
    return next(r for r in hub.b.provider_hub_state()["providers"] if r["id"] == pid)


def test_save_inactive_preset_offline_keeps_coach_and_remembers_connection(hub, caplog):
    b, svc = hub.b, hub.svc
    res = b.save_provider_config(
        "siliconflow", "", "https://proxy.example/v1/chat/completions", "my-model", SECRET,
    )
    assert res["ok"] and res["saved"] and res["configured"]
    assert svc.provider_id == "deepseek"
    assert (svc.coach.base_url, svc.coach.model) == ("https://legacy.example/v1", "legacy-model")
    row = _row(hub, "siliconflow")
    assert row["base_url"] == "https://proxy.example/v1" and row["model"] == "my-model"
    assert not row["current"] and row["configured"]
    assert SECRET not in json.dumps(res) + json.dumps(b.provider_hub_state()) + caplog.text
    assert SECRET not in hub.path.read_text(encoding="utf-8")
    assert dotenv_values(hub.env)["SILICONFLOW_API_KEY"] == SECRET
    b.set_provider("siliconflow")
    assert (svc.provider_id, svc.coach.base_url, svc.coach.model) == (
        "siliconflow", "https://proxy.example/v1", "my-model",
    )
    b.set_provider("deepseek")
    assert (svc.coach.base_url, svc.coach.model) == ("https://legacy.example/v1", "legacy-model")
    b.set_provider("siliconflow")
    assert svc.coach.api_key == SECRET and svc.coach.model == "my-model"


def test_custom_offline_save_edit_select_and_delete_while_inactive(hub):
    b = hub.b
    res = b.save_provider_config("", "家里的 Ollama", "http://127.0.0.1:11434/v1", "qwen3", SECRET)
    pid = res["provider_id"]
    assert pid.startswith("custom:") and res["saved"] and res["configured"]
    assert hub.svc.provider_id == "deepseek"
    assert yaml.safe_load(hub.path.read_text(encoding="utf-8"))["coach"]["provider"] == "deepseek"
    assert _row(hub, pid)["current"] is False
    assert b.set_provider(pid)["ok"] and hub.svc.provider_id == "custom"
    assert hub.svc.coach.api_key == SECRET
    b.set_provider("deepseek")
    assert b.save_provider_config(pid, "重命名", "https://new.example/v1", "new-model", "")["configured"]
    assert hub.svc.provider_id == "deepseek" and hub.svc.coach.model == "legacy-model"
    assert b.delete_custom(pid.split(":", 1)[1])["ok"]
    assert hub.svc.provider_id == "deepseek" and hub.svc.coach.model == "legacy-model"
    assert not customs.list_customs() and SECRET not in hub.env.read_text(encoding="utf-8")


def test_edit_active_custom_preserves_selection_and_other_custom_deletion(hub):
    b = hub.b
    first = b.save_provider_config("", "A", "https://a.example/v1", "a", SECRET)["provider_id"]
    second = b.save_provider_config("", "B", "https://b.example/v1", "b", "")["provider_id"]
    b.set_provider(first)
    b.save_provider_config(second, "B2", "https://b.example/v2", "b2", "")
    assert b.provider_hub_state()["active_provider"] == first
    assert hub.svc.coach.model == "a"
    b.save_provider_config(first, "A2", "https://a.example/v2", "a2", "")
    assert b.provider_hub_state()["active_provider"] == first and hub.svc.coach.model == "a2"
    assert b.delete_custom(second.split(":", 1)[1])["ok"]
    assert hub.svc.provider_id == "custom" and hub.svc.coach.model == "a2"


@pytest.mark.parametrize("pid", ["siliconflow", ""])
def test_invalid_key_never_mutates_configuration_or_key_file(hub, pid):
    before = hub.path.read_bytes(), hub.env.read_bytes()
    res = hub.b.save_provider_config(pid, "test", "https://example.com/v1", "m", "bad\nKEY=secret")
    assert not res["ok"] and not res["saved"] and res["field"] == "key"
    assert (hub.path.read_bytes(), hub.env.read_bytes()) == before
    assert hub.svc.provider_id == "deepseek"


@pytest.mark.parametrize("url", [
    "https://user:secret@example.com/v1", "https://example.com/v1?api_key=secret",
    "https://example.com:wrong/v1", "https://example.com/v 1",
])
def test_credential_bearing_or_invalid_urls_are_rejected_without_echo(hub, url):
    before = hub.path.read_bytes()
    res = hub.b.save_provider_config("siliconflow", "", url, "model", SECRET)
    assert not res["ok"] and res["field"] == "url" and "secret" not in str(res)
    assert hub.path.read_bytes() == before and hub.env.read_text() == ""


def test_probe_is_optional_retains_saved_key_on_failure_and_uses_target(hub, monkeypatch):
    seen = []

    def probe(key, url, model, **kw):
        seen.append((key, url, model))
        return {"ok": False, "kind": "network", "reason_zh": "联网失败", "ms": None}

    monkeypatch.setattr(keycheck, "test_key", probe)
    res = hub.b.save_provider_config(
        "siliconflow", "", "https://sf.example/v1", "test-model", SECRET, True,
    )
    assert res["ok"] and res["saved"] and not res["test"]["ok"]
    assert seen == [(SECRET, "https://sf.example/v1", "test-model")]
    assert _row(hub, "siliconflow")["configured"]
    assert hub.svc.provider_id == "deepseek" and hub.svc.coach.model == "legacy-model"
    assert hub.b._last_test == {} and SECRET not in json.dumps(res)
    hub.b.test_provider_config("siliconflow")
    assert len(seen) == 2 and hub.svc.provider_id == "deepseek"


def test_blank_key_retains_existing_and_delete_can_target_inactive_shared_key(hub):
    b = hub.b
    b.save_provider_config("stepfun_plan", "", "https://step.example/v1", "step-model", SECRET)
    res = b.save_provider_config("stepfun_plan", "", "https://step.example/v2", "updated", "")
    assert res["configured"] and dotenv_values(hub.env)["STEPFUN_API_KEY"] == SECRET
    assert _row(hub, "stepfun")["configured"]
    assert b.delete_provider_key("stepfun")["ok"]
    assert not _row(hub, "stepfun_plan")["configured"]
    assert hub.svc.provider_id == "deepseek" and hub.svc.coach.model == "legacy-model"


def test_hub_contains_domestic_presets_and_unknown_ids_do_not_mutate(hub):
    ids = {r["id"] for r in hub.b.provider_hub_state()["providers"]}
    assert {"dashscope", "zhipu", "moonshot", "volcengine", "minimax", "yi", "baichuan"} <= ids
    before = hub.path.read_bytes(), hub.env.read_bytes()
    for bad in ("unknown", "custom", "custom:missing"):
        assert not hub.b.save_provider_config(bad, "", "https://x.example/v1", "m", SECRET)["ok"]
        assert not hub.b.test_provider_config(bad)["ok"]
        assert not hub.b.delete_provider_key(bad)["ok"]
        assert not hub.b.set_provider(bad)["ok"]
    assert (hub.path.read_bytes(), hub.env.read_bytes()) == before


def test_model_change_keeps_saved_url(hub):
    hub.b.save_provider_config("deepseek", "", "https://new.example/v1", "old", "")
    assert hub.b.save_coach_model("new")["ok"]
    assert hub.svc.coach.base_url == "https://new.example/v1"
    assert provider_store.preset_values("deepseek")["model"] == "new"


def test_legacy_settings_writer_updates_an_existing_hub_entry(hub):
    hub.b.save_provider_config("deepseek", "", "https://hub.example/v1", "hub-model", "")
    config.save_coach_choice("deepseek", "legacy-ui-model", "https://legacy-ui.example/v1")
    hub.svc.reload_llm()
    assert hub.svc.coach.model == "legacy-ui-model"
    assert hub.svc.coach.base_url == "https://legacy-ui.example/v1"
    assert _row(hub, "deepseek")["model"] == "legacy-ui-model"


def test_deleting_last_active_custom_restores_the_saved_default_preset(hub):
    res = hub.b.save_provider_config("", "custom", "https://custom.example/v1", "custom-model", "")
    hub.b.set_provider(res["provider_id"])
    assert hub.b.delete_custom(res["provider_id"].split(":", 1)[1])["ok"]
    assert hub.svc.provider_id == "deepseek" and hub.svc.coach.model == "legacy-model"
    assert hub.svc.coach.base_url == "https://legacy.example/v1"


def test_key_probe_honors_mandatory_reasoning_model_requirements():
    seen = []

    class Client:
        def __init__(self, **kw):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: seen.append(kw)))

    assert keycheck.test_key(
        SECRET, "https://api.moonshot.cn/v1", "kimi-k3.1-pro",
        provider_id="moonshot", client_factory=Client,
    )["ok"]
    assert seen[0]["max_tokens"] >= 8192 and seen[0]["temperature"] == 1.0


def test_switching_presets_never_rewrites_nested_custom_connection_fields(hub):
    first = hub.b.save_provider_config("", "one", "https://one.example/v1", "one-model", "")
    second = hub.b.save_provider_config("", "two", "https://two.example/v2", "two-model", "")
    original = [entry.as_dict() for entry in customs.list_customs()]
    assert hub.svc.provider_id == "deepseek"
    assert hub.b.set_provider("siliconflow")["ok"]
    assert [entry.as_dict() for entry in customs.list_customs()] == original
    data = yaml.safe_load(hub.path.read_text(encoding="utf-8"))
    assert data["coach"]["provider"] == "siliconflow"
    assert data["coach"]["model"] == _row(hub, "siliconflow")["model"]
    assert data["coach"]["base_url"] == _row(hub, "siliconflow")["base_url"]
    assert hub.b.save_coach_model("my-sf-model")["ok"]
    assert [entry.as_dict() for entry in customs.list_customs()] == original
    assert hub.b.set_provider(first["provider_id"])["ok"]
    assert hub.b.set_provider("deepseek")["ok"]
    assert [entry.as_dict() for entry in customs.list_customs()] == original
    assert hub.b.set_provider(second["provider_id"])["ok"]
    assert hub.svc.coach.model == "two-model"


@pytest.mark.parametrize("pid", ["", "siliconflow"])
def test_key_storage_failure_reports_saved_connection_and_stable_id(hub, monkeypatch, pid):
    class ReadOnlyStore:
        def set(self, *args):
            raise keystore.KeyStoreError(keystore.MSG_WRITE)

        def has(self, var):
            return False

        def get(self, var):
            return ""

    monkeypatch.setattr(keystore, "_store", ReadOnlyStore())
    res = hub.b.save_provider_config(pid, "retry me", "https://saved.example/v1", "saved-model", SECRET)
    assert not res["ok"] and res["saved"] and res["field"] == "key"
    assert res["provider_id"] and "接口配置已保存" in res["reason_zh"]
    assert _row(hub, res["provider_id"])["model"] == "saved-model"
    assert hub.svc.provider_id == "deepseek"
    retry = hub.b.save_provider_config(
        res["provider_id"], "retry me", "https://saved.example/v1", "saved-model", SECRET,
    )
    assert retry["provider_id"] == res["provider_id"]
    assert len(customs.list_customs()) == (1 if not pid else 0)


def test_settings_write_retries_a_short_windows_sharing_violation(tmp_path, monkeypatch):
    tmp = tmp_path / "settings.yaml.tmp"
    dst = tmp_path / "settings.yaml"
    tmp.write_text("saved", encoding="utf-8")
    replace = os.replace
    calls = []

    def temporarily_locked(source, target):
        calls.append(target)
        if len(calls) < 3:
            raise PermissionError("locked")
        replace(source, target)

    monkeypatch.setattr(os, "replace", temporarily_locked)
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    config.replace_settings_file(tmp, dst)
    assert len(calls) == 3 and dst.read_text(encoding="utf-8") == "saved"
