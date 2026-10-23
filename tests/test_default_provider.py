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


def test_env_provider_and_model_are_ignored(monkeypatch, tmp_path, caplog):
    """PRD D9: .env only holds keys; settings.yaml picks provider / model."""
    import logging

    from dodoclaw import config

    _settings(monkeypatch, tmp_path, 'coach:\n  provider: "stepfun_plan"\n')
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_MODEL", "some-other-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("STEPFUN_API_KEY", "sk-step-SECRET-123")
    monkeypatch.setattr(config, "_ignored_logged", False)
    caplog.set_level(logging.INFO, logger="dodoclaw.config")
    pid, _n, key, url, model = Settings(_env_file=None).resolve_llm()
    assert pid == "stepfun_plan" and url.endswith("/step_plan/v1") and model != "some-other-model"
    assert key == "sk-step-SECRET-123"
    lines = [r.getMessage() for r in caplog.records if "已忽略" in r.getMessage()]
    assert len(lines) == 1 and "LLM_PROVIDER" in lines[0] and "settings.yaml" in lines[0]
    assert "deepseek" not in lines[0] and "SECRET" not in caplog.text
    Settings(_env_file=None).resolve_llm()  # logged only once
    assert len([r for r in caplog.records if "已忽略" in r.getMessage()]) == 1


def test_env_provider_does_not_override_code_default(monkeypatch, tmp_path):
    _settings(monkeypatch, tmp_path, None)
    monkeypatch.setenv("LLM_PROVIDER", "stepfun_plan")
    pid, _n, _k, _u, model = Settings(_env_file=None).resolve_llm()
    assert (pid, model) == ("deepseek", "deepseek-flash")


def test_yaml_model_and_base_url_are_used(monkeypatch, tmp_path):
    s = _settings(
        monkeypatch, tmp_path,
        'coach:\n  provider: "stepfun_plan"\n  model: "step-3.5-flash"\n  base_url: "https://proxy.example/v1/"\n',
    )
    _pid, _n, _k, url, model = s.resolve_llm()
    assert (url, model) == ("https://proxy.example/v1", "step-3.5-flash")


def test_env_example_has_no_provider_or_model_lines():
    names = [ln.split("=", 1)[0].strip() for ln in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    for bad in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "XAI_MODEL", "XAI_BASE_URL"):
        assert bad not in names


def test_save_coach_choice_keeps_comments_and_other_keys(monkeypatch, tmp_path):
    from dodoclaw import config

    cfg = tmp_path / "settings.yaml"
    cfg.write_text(
        'coach:\n  language: "zh-CN"\n  # 注释\n  provider: "deepseek"\n  base_url: "https://old/v1"\n'
        '  max_reply_chars: 400\n\nui:\n  positions: [2]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "reload_settings", lambda: None)
    config.save_coach_choice("stepfun_plan", "step-3.7-flash", "")
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["coach"]["provider"] == "stepfun_plan" and data["coach"]["model"] == "step-3.7-flash"
    assert "base_url" not in data["coach"] and data["coach"]["max_reply_chars"] == 400
    assert data["ui"] == {"positions": [2]} and "# 注释" in cfg.read_text(encoding="utf-8")


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
