from dodoclaw.providers import (
    DEFAULT_PROVIDER_ID,
    chat_extra_body,
    chat_max_tokens,
    chat_temperature,
    get_provider,
    list_providers,
    provider_id_from_name,
    resolve_llm_runtime,
)


def test_default_is_deepseek_flash():
    assert DEFAULT_PROVIDER_ID == "deepseek"
    p = get_provider(None)
    assert p.id == "deepseek" and p.default_model == "deepseek-flash"
    assert p.base_url == "https://api.deepseek.com"


def test_stepfun_plan_still_available():
    p = get_provider("stepfun_plan")
    assert p.id == "stepfun_plan" and "step_plan" in p.base_url


def test_cn_providers_present():
    ids = {p.id for p in list_providers()}
    for need in (
        "stepfun_plan",
        "stepfun",
        "deepseek",
        "dashscope",
        "zhipu",
        "moonshot",
        "siliconflow",
        "volcengine",
        "minimax",
        "yi",
        "baichuan",
        "custom",
    ):
        assert need in ids


def test_aliases():
    assert get_provider("coding_plan").id == "stepfun_plan"
    assert get_provider("qwen").id == "dashscope"
    assert get_provider("kimi").id == "moonshot"
    assert get_provider("doubao").id == "volcengine"


def test_resolve_runtime_env():
    env = {
        "LLM_API_KEY": "sk-test",
        "STEPFUN_API_KEY": "sk-step",
    }
    spec, key, url, model = resolve_llm_runtime(
        "stepfun_plan", env_get=env
    )
    assert spec.id == "stepfun_plan"
    assert key == "sk-step"  # the provider's own key beats the generic LLM_API_KEY
    assert url.endswith("/step_plan/v1")
    assert model
    assert resolve_llm_runtime("stepfun_plan", env_get={"LLM_API_KEY": "sk-test"})[1] == "sk-test"


def test_no_cross_vendor_key_fallback():
    """After switching to DeepSeek, a StepFun key must not be sent to DeepSeek."""
    env = {"STEPFUN_API_KEY": "sk-step", "XAI_API_KEY": "xai-1"}
    assert resolve_llm_runtime("deepseek", env_get=env)[1] == ""
    assert resolve_llm_runtime("xai", env_get=env)[1] == "xai-1"


def test_provider_id_from_name():
    name = get_provider("deepseek").name
    assert provider_id_from_name(name) == "deepseek"


def test_resolve_runtime_ignores_env_model_and_base_url():
    """PRD D9: only keys come from the environment."""
    env = {"STEPFUN_API_KEY": "sk-step", "LLM_MODEL": "x-model", "LLM_BASE_URL": "https://x.invalid/v1"}
    spec, key, url, model = resolve_llm_runtime("stepfun_plan", env_get=env)
    assert key == "sk-step" and url == spec.base_url.rstrip("/") and model == spec.default_model


def test_mandatory_reasoning_models_keep_final_answer_budget():
    for provider, model in (
        ("zhipu", "glm-5.3-flash"),
        ("moonshot", "kimi-k3.1-pro"),
        ("minimax", "MiniMax-M3.1-Flash"),
    ):
        assert chat_extra_body(provider, model) == {"reasoning_effort": "low"}
        assert chat_max_tokens(provider, model, default=8) == 8192
        assert chat_max_tokens(provider, model, default=16384) == 16384


def test_optional_reasoning_defaults_use_short_answer_mode():
    assert chat_extra_body("minimax") == {"thinking": {"type": "disabled"}}
    assert chat_extra_body("volcengine") == {"thinking": {"type": "disabled"}}
    assert chat_max_tokens("minimax", default=500) == 500
    assert chat_max_tokens("custom", "glm-5.3-flash", default=8) == 8
    assert chat_extra_body("custom", "MiniMax-M3") == {}


def test_kimi_fixed_temperature_does_not_change_other_providers():
    assert chat_temperature("moonshot") == 1.0
    assert chat_temperature("kimi", "kimi-k3.1-pro-highspeed", default=0.7) == 1.0
    assert chat_temperature("moonshot", "moonshot-v1-8k", default=0.7) == 0.7
    assert chat_temperature("custom", "kimi-k3.1-pro", default=0.7) == 0.7
    assert chat_extra_body("deepseek", "deepseek-flash") == {"thinking": {"type": "disabled"}}
    assert chat_extra_body("moonshot", "moonshot-v1-8k") == {}
