"""API-key status for the settings page — booleans only, never the key itself.

Rules: nothing in this module returns, logs or prints a key value, and nothing
writes to ``.env`` (saving a key goes through ``webui.keystore``).
``reload_env`` only *reads* the file.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from dodoclaw.providers import PROVIDERS, get_provider

logger = logging.getLogger(__name__)

KEY_ENVS: tuple[str, ...] = tuple(sorted({p.key_env for p in PROVIDERS.values()} | {"LLM_API_KEY"}))
# Coach providers that also offer cloud speech recognition with the same key
STT_PROVIDERS = {"stepfun_plan", "stepfun", "siliconflow"}


# 服务商 dropdown (PRD D10, design/v2 README): exactly these five, in this order.
# (id, name, tag in the field, tag in the menu, hint). Other presets (通义、Kimi、
# 自定义…) are not offered here; if settings.yaml names one, it is still shown
# as the current provider and works as before.
# Order: DeepSeek → 硅基流动 → 阶跃… → xAI → OpenAI. 「＋ 自定义」 is appended in
# list_providers (not a fixed ProviderSpec row).
PICKER: tuple[tuple[str, str, str, str, str], ...] = (
    ("deepseek", "DeepSeek", "推荐", "默认 · 推荐", ""),
    ("siliconflow", "硅基流动", "OpenAI 兼容", "OpenAI 兼容", "国内直连"),
    ("stepfun_plan", "阶跃 Step Plan", "订阅制", "订阅制", "和“阶跃按量”共用一个阶跃 Key"),
    ("stepfun", "阶跃按量", "按量计费", "按量计费", "自带云端语音识别"),
    ("xai", "xAI (Grok)", "国内需代理", "国内需代理", "SuperGrok 会员不含 API 额度"),
    ("openai", "OpenAI", "国内需代理", "国内需代理", "ChatGPT Plus 不含 API 额度"),
)
PICKER_IDS: tuple[str, ...] = tuple(x[0] for x in PICKER)
_BY_ID = {x[0]: x for x in PICKER}
# short names used inside sentences (“去申请 阶跃 Key”, “切回 DeepSeek”)
_SHORT = {
    "deepseek": "DeepSeek",
    "siliconflow": "硅基流动",
    "stepfun_plan": "阶跃",
    "stepfun": "阶跃",
    "xai": "xAI",
    "openai": "OpenAI",
    "custom": "自定义",
}


def provider_label(provider_id: str) -> str:
    spec = get_provider(provider_id)
    return _BY_ID[spec.id][1] if spec.id in _BY_ID else spec.name


def provider_tag(provider_id: str) -> str:
    spec = get_provider(provider_id)
    return _BY_ID[spec.id][2] if spec.id in _BY_ID else ""


def provider_short(provider_id: str) -> str:
    spec = get_provider(provider_id)
    return _SHORT.get(spec.id, provider_label(spec.id))


def shares_key_with(provider_id: str) -> list[str]:
    env = get_provider(provider_id).key_env
    return [pid for pid in PICKER_IDS if pid != provider_id and get_provider(pid).key_env == env]


def list_providers(current: str = "", current_configured: bool = False) -> list[dict[str, Any]]:
    """Preset dropdown rows + a trailing 「＋ 自定义」 action. Booleans only."""
    from dodoclaw.webui import customs, keystore

    cur_raw = (current or "").strip().lower()
    cur = get_provider(cur_raw).id if cur_raw and cur_raw != "custom" else cur_raw
    active_custom = customs.active_custom_id() if cur == "custom" else ""
    out = []
    for pid, name, _tag, menu_tag, hint in PICKER:
        spec = get_provider(pid)
        configured = keystore.has_key(spec.key_env) or (pid == cur and current_configured)
        # Menu subtitle: host · 已配置/未配置 · hint (design D12)
        host = ""
        try:
            from urllib.parse import urlparse
            host = (urlparse(spec.base_url).hostname or "") 
        except Exception:
            host = ""
        ds_bits = [b for b in (host, ("已配置" if configured else "未配置"), hint) if b]
        out.append({
            "id": pid,
            "name": name,
            "tag": menu_tag,
            "model": spec.default_model,
            "models": spec.model_choices(),
            "base_url": spec.base_url,
            "configured": bool(configured),
            "shares_key_with": shares_key_with(pid),
            "hint": hint,
            "subtitle": " · ".join(ds_bits),
            "apply_url": spec.apply_url(),
            "current": pid == cur,
            "kind": "preset",
        })
    # Trailing action — not a real provider id for set_provider
    out.append({
        "id": "__add_custom__",
        "name": "＋ 自定义（OpenAI 兼容）",
        "tag": "",
        "model": "",
        "models": [],
        "base_url": "",
        "configured": False,
        "shares_key_with": [],
        "hint": "填接口地址和模型 ID，可保存多家",
        "subtitle": "填接口地址和模型 ID，可保存多家",
        "apply_url": "",
        "current": False,
        "kind": "add_custom",
    })
    return out


# 测试失败的说明块 (design/v2 README “测试失败的原因和指引”). link: what the
# right-hand action does — key | topup | log | "" (none).
_GUIDE: dict[str, tuple[str, str, str]] = {
    "plan_expired": ("Key 已保存，但账号没有有效订阅。续订后点“重新测试”，不用重填；也可以换成“阶跃按量”（同一个 Key）或 DeepSeek。", "去续订", "topup"),
    "auth": ("可能复制少了一截，或在平台上被删了。点“更换 Key”重新粘贴。", "去申请", "key"),
    "balance": ("去平台充值后点“重新测试”，不用重填。", "去充值", "topup"),
    "rate_limit": ("过一分钟再点“重新测试”。", "", ""),
    "network": ("xAI / OpenAI 在国内要开代理；开好后点“重新测试”。", "", ""),
    "bad_address": ("连不上这个接口地址，检查一下地址和网络后点“重新测试”。", "", ""),
    "not_found": ("模型名或接口地址不对。把服务商重新选一次就恢复默认；自定义接口请在上方改接口地址和模型 ID，改完点“重新测试”。", "", ""),
    "unknown": ("点“重新测试”；还不行就把日志发给开发者。", "打开日志", "log"),
    "http": ("点“重新测试”；还不行就把日志发给开发者。", "打开日志", "log"),
}


def test_guide(kind: str) -> dict[str, str]:
    """{detail_zh, link_zh, link} for a failed test. Fixed Chinese, never exception text."""
    detail, link_zh, link = _GUIDE.get(kind or "", _GUIDE["unknown"])
    return {"detail_zh": detail + "提醒不受影响。", "link_zh": link_zh, "link": link}


def env_flags(env: dict[str, str] | None = None) -> dict[str, bool]:
    env = os.environ if env is None else env
    return {k: bool((env.get(k) or "").strip()) for k in KEY_ENVS}


def env_names_in_file(path: Path) -> set[str]:
    """Variable names present in .env (values are not kept)."""
    if not path.exists():
        return set()
    from dotenv import dotenv_values

    return {k for k in dotenv_values(path).keys() if k}


def reload_env_file(path: Path, previously_from_file: set[str]) -> set[str]:
    """Re-read .env into os.environ (override=True). Read-only on the file.

    Key variables that came from the file before but were deleted from it are
    dropped from the process environment, so removing a line really clears it.
    Returns the set of variable names now present in the file.
    """
    names = env_names_in_file(path)
    for k in previously_from_file - names:
        if k in KEY_ENVS:
            os.environ.pop(k, None)
    if path.exists():
        from dotenv import load_dotenv

        load_dotenv(path, override=True)
    return names


def key_status(
    provider_id: str,
    provider_name: str,
    api_key: str,
    model: str = "",
    *,
    base_url: str = "",
    custom_id: str = "",
) -> dict[str, Any]:
    """Booleans and names only. No hint about where the key is stored (README D10)."""
    from dodoclaw.webui import customs

    raw = (provider_id or "").strip().lower()
    is_custom = raw == "custom"
    spec = get_provider("custom" if is_custom else provider_id)
    flags = env_flags()
    configured = bool((api_key or "").strip())
    cp = customs.get_custom(custom_id) if is_custom else None
    name = (
        (cp.display_name if cp else "自定义接口")
        if is_custom
        else (provider_label(spec.id) if spec.id in _BY_ID else (provider_name or spec.name))
    )
    key_env = cp.key_env if cp else spec.key_env
    sf_key = flags.get("SILICONFLOW_API_KEY", False) or (
        spec.id == "siliconflow" and configured
    )
    step_key = flags.get("STEPFUN_API_KEY", False) or (
        spec.id in {"stepfun_plan", "stepfun"} and configured
    )
    return {
        "configured": configured,
        "provider": "custom" if is_custom else spec.id,
        "provider_name": name,
        "provider_short": provider_short("custom" if is_custom else spec.id),
        "provider_tag": "OpenAI 兼容" if is_custom else provider_tag(spec.id),
        "in_picker": (not is_custom) and spec.id in _BY_ID,
        "model": (cp.model if cp else "") or model or spec.default_model,
        "base_url": (cp.base_url if cp else "") or base_url or spec.base_url,
        "models": [] if is_custom else spec.model_choices(),
        "default_model": spec.default_model,
        "key_env": key_env,
        "apply": bool(spec.apply_url()) if not is_custom else False,
        "has_stt": (spec.id in STT_PROVIDERS) or sf_key,
        "stepfun_key": step_key,
        "siliconflow_key": bool(sf_key),
        "custom_id": cp.id if cp else "",
        "is_custom": is_custom,
    }


def test_key(
    api_key: str,
    base_url: str,
    model: str,
    *,
    client_factory: Callable[..., Any] | None = None,
    timeout: float = 15.0,
    extra_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One tiny chat completion. Returns {ok, kind, reason_zh, ms} — never the key."""
    from dodoclaw.coach.errors import NO_KEY, classify

    if not (api_key or "").strip():
        return {"ok": False, "kind": "no_key", "reason_zh": NO_KEY, "ms": None}
    if client_factory is None:
        from openai import OpenAI as client_factory  # noqa: N813
    t0 = time.time()
    try:
        client = client_factory(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "1"}],
            max_tokens=8,
            extra_body=extra_body or None,
        )
    except Exception as exc:
        # class name + status only; exception text can echo part of the key
        logger.warning("key test failed: %s status=%s", type(exc).__name__, getattr(exc, "status_code", None))
        err = classify(exc)
        return {"ok": False, "kind": err["kind"], "reason_zh": err["reason_zh"], "ms": None}
    return {"ok": True, "kind": "ok", "reason_zh": "连接正常", "ms": int((time.time() - t0) * 1000)}
