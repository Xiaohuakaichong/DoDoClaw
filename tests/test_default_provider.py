"""New-user default = DeepSeek (deepseek-flash, thinking off); existing configs keep their provider."""

from __future__ import annotations

from pathlib import Path

import yaml

from dodoclaw import paths
from dodoclaw.config import Settings
from dodoclaw.providers import chat_extra_body

ROOT = Path(__file__).resolve().parents[1]


def test_thinking_disabled_for_deepseek_only():
    assert chat_extra_body("deepseek", "deepseek-flash") == {"thinking": {"type": "disabled"}}
    assert chat_extra_body(None) == {"thinking": {"type": "disabled"}}  # default provider
    assert chat_extra_body("stepfun_plan", "step-3.7-flash") == {}
    assert chat_extra_body("deepseek", "my-proxy-model") == {}


def _settings(monkeypatch, tmp_path, yaml_text: str | None) -> Settings:
    for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "settings.yaml"
    if yaml_text is not None:
        cfg.write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr(Settings, "yaml_path", lambda self: cfg)
    return Settings(_env_file=None)


def test_no_config_resolves_to_deepseek_flash(monkeypatch, tmp_path):
    pid, _name, _key, url, model = _settings(monkeypatch, tmp_path, None).resolve_llm()
    assert (pid, url, model) == ("deepseek", "https://api.deepseek.com", "deepseek-flash")


def test_existing_yaml_provider_is_kept(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path, 'coach:\n  provider: "stepfun_plan"\n')
    assert s.resolve_llm()[0] == "stepfun_plan"


def test_env_provider_still_wins(monkeypatch, tmp_path):
    s = _settings(monkeypatch, tmp_path, 'coach:\n  provider: "deepseek"\n')
    monkeypatch.setenv("LLM_PROVIDER", "stepfun_plan")
    assert Settings(_env_file=None).resolve_llm()[0] == "stepfun_plan"


def test_default_template_is_deepseek():
    tpl = yaml.safe_load((ROOT / "config" / "settings.default.yaml").read_text(encoding="utf-8"))
    assert tpl["coach"]["provider"] == "deepseek"


def _fake_layout(monkeypatch, tmp_path):
    bundle, app = tmp_path / "bundle", tmp_path / "app"
    (bundle / "config").mkdir(parents=True)
    (bundle / "config" / "settings.default.yaml").write_text('coach:\n  provider: "deepseek"\n', encoding="utf-8")
    (bundle / "config" / "gamestate_integration_dodoclaw.cfg").write_text("cfg", encoding="utf-8")
    monkeypatch.setattr(paths, "bundle_dir", lambda: bundle)
    monkeypatch.setattr(paths, "app_dir", lambda: app)
    return app


def test_seed_new_user_from_template(monkeypatch, tmp_path):
    app = _fake_layout(monkeypatch, tmp_path)
    paths.ensure_user_config_seeded()
    assert "deepseek" in (app / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert (app / "config" / "gamestate_integration_dodoclaw.cfg").exists()


def test_seed_never_overwrites_existing_settings(monkeypatch, tmp_path):
    app = _fake_layout(monkeypatch, tmp_path)
    (app / "config").mkdir(parents=True)
    mine = 'coach:\n  provider: "stepfun_plan"\n'
    (app / "config" / "settings.yaml").write_text(mine, encoding="utf-8")
    paths.ensure_user_config_seeded()
    assert (app / "config" / "settings.yaml").read_text(encoding="utf-8") == mine
