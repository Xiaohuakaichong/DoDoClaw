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
    assert key == "sk-test"
    assert url.endswith("/step_plan/v1")
    assert model


def test_provider_id_from_name():
    name = get_provider("deepseek").name
    assert provider_id_from_name(name) == "deepseek"
