"""OpenAI-compatible LLM provider presets (CN mainland + common global)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    name: str
    base_url: str
    default_model: str
    models: tuple[str, ...] = ()
    # Preferred env var for this provider's API key (also accepts LLM_API_KEY)
    key_env: str = "LLM_API_KEY"
    region: str = "cn"  # cn | global | custom
    note: str = ""
    docs_url: str = ""
    # Page where the user creates an API key (设置页“去申请”); "" = fall back to docs_url
    key_url: str = ""
    # Page to top up / renew (测试失败“去充值 / 去续订”); "" = fall back to key_url
    billing_url: str = ""
    # Send {"thinking": {"type": "disabled"}} on chat completions (DeepSeek V4 models think by default)
    thinking_off: bool = False

    def apply_url(self) -> str:
        """Where “去申请” goes: the key page, else the docs. https only."""
        for u in (self.key_url, self.docs_url):
            if u.startswith("https://"):
                return u
        return ""

    def topup_url(self) -> str:
        """Where “去充值 / 去续订” goes. https only."""
        return self.billing_url if self.billing_url.startswith("https://") else self.apply_url()

    def model_choices(self) -> list[str]:
        items = list(self.models) if self.models else [self.default_model]
        if self.default_model not in items:
            items.insert(0, self.default_model)
        return items


# Order matters: shown in GUI dropdown (CN-first for community)
PROVIDERS: dict[str, ProviderSpec] = {
    "stepfun_plan": ProviderSpec(
        id="stepfun_plan",
        name="阶跃星辰 Step Plan（Coding Plan）",
        base_url="https://api.stepfun.com/step_plan/v1",
        default_model="step-3.7-flash",
        models=(
            "step-3.7-flash",
            "step-3.5-flash",
            "step-3.5-flash-2603",
        ),
        key_env="STEPFUN_API_KEY",
        region="cn",
        note="订阅 Coding Plan / Step Plan 额度专用端点（国内）",
        docs_url="https://platform.stepfun.com/docs/zh/step-plan/quick-start",
        key_url="https://platform.stepfun.com/interface-key",
        billing_url="https://platform.stepfun.com/step-plan",
    ),
    "stepfun": ProviderSpec(
        id="stepfun",
        name="阶跃星辰 StepFun（标准 API）",
        base_url="https://api.stepfun.com/v1",
        default_model="step-2-mini",
        models=("step-2-mini", "step-1.5v-mini", "step-1v-8k", "step-1-8k"),
        key_env="STEPFUN_API_KEY",
        region="cn",
        note="按量计费开放平台，非 Step Plan 订阅端点",
        docs_url="https://platform.stepfun.com/docs/zh/guides/developer/openai",
        key_url="https://platform.stepfun.com/interface-key",
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        default_model="deepseek-flash",
        models=("deepseek-flash", "deepseek-v4-pro"),
        key_env="DEEPSEEK_API_KEY",
        region="cn",
        note="默认 deepseek-flash，关闭思考模式（回答更快更省）",
        thinking_off=True,
        docs_url="https://platform.deepseek.com/api-docs/",
        key_url="https://platform.deepseek.com/api_keys",
        billing_url="https://platform.deepseek.com/top_up",
    ),
    "dashscope": ProviderSpec(
        id="dashscope",
        name="通义千问（阿里云 DashScope）",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        models=("qwen-plus", "qwen-turbo", "qwen-max", "qwen-long", "qwen2.5-72b-instruct"),
        key_env="DASHSCOPE_API_KEY",
        region="cn",
        docs_url="https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope",
    ),
    "zhipu": ProviderSpec(
        id="zhipu",
        name="智谱 GLM",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4-flash",
        models=("glm-4-flash", "glm-4-air", "glm-4-plus", "glm-4-long", "glm-4"),
        key_env="ZHIPU_API_KEY",
        region="cn",
        docs_url="https://open.bigmodel.cn/dev/api",
    ),
    "moonshot": ProviderSpec(
        id="moonshot",
        name="月之暗面 Kimi（Moonshot）",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        models=(
            "moonshot-v1-8k",
            "moonshot-v1-32k",
            "moonshot-v1-128k",
            "kimi-latest",
        ),
        key_env="MOONSHOT_API_KEY",
        region="cn",
        docs_url="https://platform.moonshot.cn/docs/api/chat",
    ),
    "siliconflow": ProviderSpec(
        id="siliconflow",
        name="硅基流动 SiliconFlow",
        base_url="https://api.siliconflow.cn/v1",
        default_model="deepseek-ai/DeepSeek-V3",
        models=(
            "deepseek-ai/DeepSeek-V3",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen2.5-72B-Instruct",
            "THUDM/glm-4-9b-chat",
        ),
        key_env="SILICONFLOW_API_KEY",
        region="cn",
        note="聚合多家开源模型，OpenAI 兼容",
        docs_url="https://docs.siliconflow.cn/",
    ),
    "volcengine": ProviderSpec(
        id="volcengine",
        name="豆包 / 火山方舟（Volcengine）",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-32k",
        models=("doubao-pro-32k", "doubao-lite-32k", "doubao-pro-128k"),
        key_env="ARK_API_KEY",
        region="cn",
        note="模型名常为接入点 Endpoint ID，请在控制台复制后覆盖",
        docs_url="https://www.volcengine.com/docs/82379",
    ),
    "minimax": ProviderSpec(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimax.chat/v1",
        default_model="MiniMax-Text-01",
        models=("MiniMax-Text-01", "abab6.5s-chat", "abab6.5-chat"),
        key_env="MINIMAX_API_KEY",
        region="cn",
        docs_url="https://platform.minimaxi.com/document/ChatCompletion%20v2",
    ),
    "yi": ProviderSpec(
        id="yi",
        name="零一万物 Yi",
        base_url="https://api.lingyiwanwu.com/v1",
        default_model="yi-lightning",
        models=("yi-lightning", "yi-large", "yi-medium", "yi-spark"),
        key_env="YI_API_KEY",
        region="cn",
        docs_url="https://platform.lingyiwanwu.com/docs",
    ),
    "baichuan": ProviderSpec(
        id="baichuan",
        name="百川 Baichuan",
        base_url="https://api.baichuan-ai.com/v1",
        default_model="Baichuan4-Turbo",
        models=("Baichuan4-Turbo", "Baichuan4-Air", "Baichuan3-Turbo"),
        key_env="BAICHUAN_API_KEY",
        region="cn",
        docs_url="https://platform.baichuan-ai.com/docs",
    ),
    "xai": ProviderSpec(
        id="xai",
        name="xAI / Grok",
        base_url="https://api.x.ai/v1",
        default_model="grok-4.5",
        models=("grok-4.5", "grok-3", "grok-3-mini"),
        key_env="XAI_API_KEY",
        region="global",
        docs_url="https://docs.x.ai",
        key_url="https://console.x.ai",
    ),
    "openai": ProviderSpec(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        models=("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini"),
        key_env="OPENAI_API_KEY",
        region="global",
        docs_url="https://platform.openai.com/docs",
        key_url="https://platform.openai.com/api-keys",
    ),
    "custom": ProviderSpec(
        id="custom",
        name="自定义（OpenAI 兼容）",
        base_url="http://127.0.0.1:8000/v1",
        default_model="default",
        models=("default",),
        key_env="LLM_API_KEY",
        region="custom",
        note="可填任意兼容接口：OneAPI / NewAPI / 本地 vLLM / Ollama 等",
    ),
}

# New-user default. coach.provider in config/settings.yaml always wins over this;
# LLM_PROVIDER in .env is ignored (PRD D9: .env only holds keys).
DEFAULT_PROVIDER_ID = "deepseek"


def chat_extra_body(provider_id: str | None, model: str = "") -> dict:
    """Provider-specific extra fields for chat.completions (e.g. DeepSeek thinking off)."""
    spec = get_provider(provider_id)
    if spec.thinking_off and (not model or model.startswith("deepseek")):
        return {"thinking": {"type": "disabled"}}
    return {}


def list_providers() -> list[ProviderSpec]:
    return list(PROVIDERS.values())


def get_provider(provider_id: str | None) -> ProviderSpec:
    if not provider_id:
        return PROVIDERS[DEFAULT_PROVIDER_ID]
    key = provider_id.strip().lower()
    # aliases
    aliases = {
        "step-plan": "stepfun_plan",
        "stepplan": "stepfun_plan",
        "step_plan": "stepfun_plan",
        "阶跃": "stepfun_plan",
        "coding_plan": "stepfun_plan",
        "coding-plan": "stepfun_plan",
        "qwen": "dashscope",
        "tongyi": "dashscope",
        "glm": "zhipu",
        "kimi": "moonshot",
        "doubao": "volcengine",
        "ark": "volcengine",
        "grok": "xai",
        "spacexai": "xai",
    }
    key = aliases.get(key, key)
    if key not in PROVIDERS:
        return PROVIDERS[DEFAULT_PROVIDER_ID]
    return PROVIDERS[key]


def provider_display_names() -> list[str]:
    return [p.name for p in list_providers()]


def provider_id_from_name(name: str) -> str:
    for p in list_providers():
        if p.name == name or p.id == name:
            return p.id
    return DEFAULT_PROVIDER_ID


def resolve_llm_runtime(
    provider_id: str | None,
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    *,
    env_get: dict[str, str] | None = None,
) -> tuple[ProviderSpec, str, str, str]:
    """
    Resolve (provider, api_key, base_url, model) from explicit values + env map.
    env_get: optional dict (defaults to os.environ); only key variables are read
    from it — base URL / model come from the arguments or the provider defaults.
    Key order: explicit api_key → the provider's own variable (key_env) →
    LLM_API_KEY (generic, legacy).
    """
    import os

    env = env_get if env_get is not None else os.environ
    spec = get_provider(provider_id)

    # Provider's own key first, then the generic LLM_API_KEY. No cross-vendor
    # fallback: a StepFun key must never be sent to DeepSeek after a switch.
    key = (api_key or "").strip()
    if not key:
        key = (env.get(spec.key_env) or "").strip()
    if not key:
        key = (env.get("LLM_API_KEY") or "").strip()

    url = (base_url or "").strip() or spec.base_url
    mdl = (model or "").strip() or spec.default_model
    return spec, key, url.rstrip("/"), mdl
