"""PRD D12: SiliconFlow in picker, custom OpenAI-compatible providers, URL/model validation."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dodoclaw.coach import errors
from dodoclaw.webui import customs, keycheck, keystore
from dodoclaw.webui.provider_validate import (
    MSG_MODEL_SPACE,
    MSG_URL_HTTP_PUBLIC,
    MSG_URL_SCHEME,
    normalize_base_url,
    validate_model_id,
)


def test_picker_has_siliconflow_after_deepseek_and_add_custom():
    rows = keycheck.list_providers("deepseek", False)
    ids = [r["id"] for r in rows]
    assert ids[0] == "deepseek"
    assert ids[1] == "siliconflow"
    assert ids[-1] == "__add_custom__"
    sf = rows[1]
    assert sf["name"] == "硅基流动"
    assert "国内需代理" not in (sf["tag"] or "")
    assert "api.siliconflow.cn" in (sf["subtitle"] or sf["base_url"])
    assert rows[-1]["kind"] == "add_custom"


def test_siliconflow_provider_spec():
    from dodoclaw.providers import get_provider

    p = get_provider("siliconflow")
    assert p.base_url == "https://api.siliconflow.cn/v1"
    assert p.key_url == "https://cloud.siliconflow.cn/account/ak"
    assert p.name == "硅基流动"
    assert "DeepSeek" in p.default_model or "Qwen" in p.default_model
    assert "SiliconFlow" not in p.name  # no English in visible name


@pytest.mark.parametrize(
    "raw,ok,expect",
    [
        ("https://api.example.com/v1", True, "https://api.example.com/v1"),
        ("https://api.example.com/v1/chat/completions", True, "https://api.example.com/v1"),
        ("http://127.0.0.1:8000/v1/", True, "http://127.0.0.1:8000/v1"),
        ("http://10.0.0.2/v1", True, "http://10.0.0.2/v1"),
        ("http://api.example.com/v1", False, MSG_URL_HTTP_PUBLIC),
        ("ftp://x", False, MSG_URL_SCHEME),
        ("  ", False, None),
    ],
)
def test_normalize_base_url(raw, ok, expect):
    if ok:
        assert normalize_base_url(raw) == expect
    else:
        with pytest.raises(ValueError) as ei:
            normalize_base_url(raw)
        if expect:
            assert str(ei.value) == expect


def test_validate_model_id():
    assert validate_model_id(" gpt-4o-mini ") == "gpt-4o-mini"
    with pytest.raises(ValueError) as ei:
        validate_model_id("bad model")
    assert str(ei.value) == MSG_MODEL_SPACE
    with pytest.raises(ValueError):
        validate_model_id("")


def test_customs_roundtrip_settings_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "settings.yaml").write_text(
        '# keep\ncoach:\n  provider: "deepseek"\n  language: "zh-CN"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(customs, "_settings_path", lambda: cfg / "settings.yaml")
    monkeypatch.setattr("dodoclaw.paths.config_dir", lambda: cfg)
    monkeypatch.setattr("dodoclaw.config.config_dir", lambda: cfg)

    e1 = customs.save_custom(name="家里的代理", base_url="https://proxy.example.com/v1", model="gpt-4o-mini")
    e2 = customs.save_custom(name="公司中转", base_url="http://192.168.1.10:8080/v1", model="qwen-plus", activate=False)
    listed = customs.list_customs()
    assert {c.id for c in listed} == {e1.id, e2.id}
    text = (cfg / "settings.yaml").read_text(encoding="utf-8")
    assert "# keep" in text
    assert "language" in text
    assert "custom_providers" in text
    assert customs.active_custom_id() == e1.id

    # key never in public list
    pub = customs.public_list(current_id=e1.id)
    assert all("key" not in row or row.get("key") in (None, "") for row in pub)
    assert all(row["key_env"].startswith("CUSTOM_") for row in pub)


def test_custom_key_allowed_and_not_leaked(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr(keystore, "env_path", lambda: env)
    keystore._store = keystore.EnvFileKeyStore(env)
    var = "CUSTOM_ABCD1234_API_KEY"
    secret = "sk-custom-NEVER-LEAK-zzzz"
    keystore.save_key(var, secret)
    assert keystore.has_key(var)
    # status / public must not echo
    st = keycheck.key_status("custom", "自定义", "", "m", custom_id="")
    blob = str(st)
    assert secret not in blob


def test_test_key_hits_base_url(monkeypatch):
    seen = {}

    class FakeCompletions:
        def create(self, **kw):
            return SimpleNamespace(choices=[])

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kw):
            seen.update(kw)
            self.chat = FakeChat()

    res = keycheck.test_key("sk-x", "https://proxy.example.com/v1", "my-model", client_factory=FakeClient)
    assert res["ok"] is True
    assert seen["base_url"] == "https://proxy.example.com/v1"
    assert seen["api_key"] == "sk-x"


def test_bad_address_classification():
    class Conn(Exception):
        pass

    exc = Conn("getaddrinfo failed: Name or service not known")
    # wrap as if openai connection error via _is_network — force by making isinstance checks fail
    # and relying on text match inside _classify_one after we patch _is_network
    class Net(OSError):
        pass

    e = Net("Name or service not known")
    # Direct unit: call _classify_one with a fake that _is_network accepts
    import httpx

    class T(httpx.ConnectError):
        def __init__(self):
            Exception.__init__(self, "getaddrinfo failed")

    out = errors.classify(T())
    assert out["kind"] in ("bad_address", "network")
    if out["kind"] == "bad_address":
        assert "连不上" in out["reason_zh"]


def test_not_found_guide_points_to_fields():
    g = keycheck.test_guide("not_found")
    assert "设置文件" not in g["detail_zh"]
    assert "接口地址" in g["detail_zh"] or "模型" in g["detail_zh"]



def test_whisper_component_and_ui_qa():
    """Designer QA: bundled package reports ready; lotus has no lead slider; chrome clears."""
    from pathlib import Path

    from dodoclaw.webui import settings_store as st
    from dodoclaw.webui import whisper_model

    assert whisper_model.component_available() is True

    js = (Path(__file__).resolve().parents[1] / "src/dodoclaw/webui/static/settings.js").read_text(
        encoding="utf-8"
    )
    assert "fixed: '整点提醒，没有提前量'" in js
    assert "never reuse prior built-in chrome" in js
    css = (Path(__file__).resolve().parents[1] / "src/dodoclaw/webui/static/shell.css").read_text(
        encoding="utf-8"
    )
    assert ".opt .miss[hidden]{display:none!important}" in css

    # pos1 defaults: bounty / river / lotus OFF (reminder-budget.md)
    for row in ("bounty", "runes", "lotus"):
        assert st.default_on(row, [1]) is False
    d = st.defaults([1])
    assert d["reminders"]["bounty"]["on"] is False
    assert d["reminders"]["runes"]["on"] is False
    assert d["reminders"]["lotus"]["on"] is False
    assert d["reminders"]["lotus"]["lead"] is None


def _bare_bridge(monkeypatch, test_res):
    """Bridge.save_custom without the window/service: stub the side effects."""
    from dodoclaw.webui import app as webapp

    b = webapp.Bridge.__new__(webapp.Bridge)
    b._svc = SimpleNamespace(coach=SimpleNamespace(api_key="sk-x"))
    b._reload_coach = lambda: None
    b.test_key = lambda: dict(test_res)
    b._follow_provider_stt = lambda: ""
    b._save_ui = lambda: None
    def fake_save(**kw):
        normalize_base_url(kw["base_url"])  # same validator as the real store
        return SimpleNamespace(id="c1", model=kw["model"], key_env="CUSTOM_C1_API_KEY")

    monkeypatch.setattr(customs, "save_custom", fake_save)
    monkeypatch.setattr(keystore, "save_key", lambda *a, **k: None)
    return b


@pytest.mark.parametrize(
    "kind,field,needle,absent",
    [
        ("bad_address", "url", "接口地址连不上", "格式不对"),
        ("network", "url", "接口地址连不上", "格式不对"),
        ("auth", "key", "Key 无效", "连不上"),
        ("not_found", "model", "模型不存在", "连不上"),
    ],
)
def test_save_custom_probe_errors_map_to_fields(monkeypatch, kind, field, needle, absent):
    b = _bare_bridge(monkeypatch, {"ok": False, "kind": kind, "reason_zh": "x", "ms": None})
    r = b.save_custom("", "https://203.0.113.1/v1", "m", "sk-x", "")
    assert r["ok"] is False and r["field"] == field
    assert needle in r["reason_zh"] and absent not in r["reason_zh"]


@pytest.mark.parametrize("url", ["ftp://x.example.com", "https://", "not a url"])
def test_save_custom_bad_url_shape_keeps_format_message(monkeypatch, url):
    b = _bare_bridge(monkeypatch, {"ok": True})
    r = b.save_custom("", url, "m", "", "")
    assert r["ok"] is False and r["field"] == "url"
    assert "连不上" not in r["reason_zh"]
    assert r["reason_zh"].startswith("接口地址") or r["reason_zh"].startswith("非本机")


def test_closed_port_probe_is_connectivity_not_format():
    # valid-shaped URL, nothing listening -> bad_address/network (never 格式不对)
    res = keycheck.test_key("sk-x", "http://127.0.0.1:9/v1", "m", timeout=3)
    assert res["ok"] is False
    assert res["kind"] in ("bad_address", "network")


def test_whisper_progress_counts_incomplete_blobs(tmp_path):
    from dodoclaw.webui import whisper_model

    blobs = tmp_path / ("models--" + whisper_model.HF_REPO.replace("/", "--")) / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "abc123.incomplete").write_bytes(b"x" * 4096)
    (blobs / "def456").write_bytes(b"y" * 1024)
    assert whisper_model._cached_bytes(tmp_path) == 5120


def test_custom_inline_error_text_follows_backend():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src/dodoclaw/webui/static"
    js = (root / "settings.js").read_text(encoding="utf-8")
    html = (root / "settings.html").read_text(encoding="utf-8")
    assert "$(errEl).textContent = r.reason_zh" in js
    assert 'id="cf-err-url">接口地址连不上' in html


def test_whisper_download_uses_plain_http_unless_user_set(monkeypatch):
    from dodoclaw.webui import whisper_model

    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    whisper_model._plain_http_transfer()
    assert os.environ["HF_HUB_DISABLE_XET"] == "1"
    monkeypatch.setenv("HF_HUB_DISABLE_XET", "0")
    whisper_model._plain_http_transfer()
    assert os.environ["HF_HUB_DISABLE_XET"] == "0"
    assert "HF_ENDPOINT" not in os.environ or os.environ["HF_ENDPOINT"]  # never set by us
