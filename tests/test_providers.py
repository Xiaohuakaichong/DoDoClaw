from dodoclaw.providers import (
    DEFAULT_PROVIDER_ID,
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
