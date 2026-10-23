"""Turn coach / key-test failures into a short Chinese reason (PRD D9).

The reason is always a fixed Chinese string (plus at most an HTTP status code);
exception text is only *searched*, never copied, so no key material can leak.
"""

from __future__ import annotations

import json
from typing import Any

SETTINGS_HREF = "settings.html#coach"

PLAN_EXPIRED = "阶跃 Step Plan 订阅已失效"
AUTH = "Key 无效或已过期"
BALANCE = "账户余额不足"
RATE_LIMIT = "请求太频繁，稍后再试"
NETWORK = "联网失败，检查网络"
NOT_FOUND = "模型名或接口地址不对（HTTP 404）"
NO_KEY = "还没填 Key"
UNKNOWN = "教练服务出错，详情见日志"

# most specific first — used to pick the best match along an exception chain
_RANK = ("plan_expired", "balance", "auth", "rate_limit", "network", "no_key", "not_found", "http", "unknown")


def _status(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


def _text(exc: BaseException) -> str:
    """Lower-cased error text to search in. Never returned to callers."""
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            parts.append(json.dumps(body, ensure_ascii=False))
        except Exception:
            parts.append(str(body))
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            parts.append(resp.text)
        except Exception:
            pass
    return " ".join(parts).lower()


def _is_network(exc: BaseException) -> bool:
    try:
        import openai

        if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
            return True
    except Exception:  # pragma: no cover
        pass
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return True
    except Exception:  # pragma: no cover
        pass
    return isinstance(exc, (TimeoutError, ConnectionError))


def _classify_one(exc: BaseException) -> tuple[str, str]:
    if _is_network(exc):
        return "network", NETWORK
    code = _status(exc)
    text = _text(exc)
    if "no active step plan subscription" in text:
        return "plan_expired", PLAN_EXPIRED
    if code == 402 or "insufficient balance" in text or "insufficient_balance" in text or "余额" in text:
        return "balance", BALANCE
    if code == 401 or "invalid api key" in text or "invalid_api_key" in text or "incorrect api key" in text:
        return "auth", AUTH
    if code == 429:
        return "rate_limit", RATE_LIMIT
    if code == 404:
        return "not_found", NOT_FOUND
    if code is not None:
        return "http", f"教练服务出错（HTTP {code}）"
    if "未设置 api key" in text:
        return "no_key", NO_KEY
    return "unknown", UNKNOWN


def _chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and cur not in out and len(out) < 8:
        out.append(cur)
        cur = cur.__cause__ or cur.__context__
    return out


def classify(exc: BaseException) -> dict[str, Any]:
    """{kind, reason_zh, href} for an LLM failure. Walks __cause__/__context__
    so a wrapped error (e.g. the coach's RuntimeError after its fallback) still
    reports the provider's original reason."""
    best = ("unknown", UNKNOWN)
    for e in _chain(exc):
        k = _classify_one(e)
        if _RANK.index(k[0]) < _RANK.index(best[0]):
            best = k
    return {"kind": best[0], "reason_zh": best[1], "href": SETTINGS_HREF}
