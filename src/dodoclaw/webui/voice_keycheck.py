"""去填 Key（只填 Key）的「保存并测试」: verify a voice vendor's Key with one
light request (GET {base}/models) before it is stored.

Returns {ok, kind, reason_zh}. reason_zh reuses coach.errors wording. The Key is
only sent in the Authorization header; it is never logged or returned.
"""

from __future__ import annotations

import logging
from typing import Any

from dodoclaw.coach import errors

logger = logging.getLogger(__name__)

MODELS_URL = {
    "siliconflow": "https://api.siliconflow.cn/v1/models",
    "stepfun": "https://api.stepfun.com/v1/models",
}
TIMEOUT = 8.0  # s — short on purpose; the UI waits for it


def verify(provider_id: str, key: str, *, timeout: float = TIMEOUT, client: Any = None) -> dict[str, Any]:
    url = MODELS_URL.get(provider_id)
    if not url:
        return {"ok": False, "kind": "invalid", "reason_zh": "没有这家服务商"}
    import httpx

    own = client is None
    c = client or httpx.Client(timeout=timeout, follow_redirects=False)
    try:
        resp = c.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    except Exception as exc:  # timeout / DNS / refused — classify, never echo
        info = errors.classify(exc)
        kind = info["kind"] if info["kind"] in ("network", "bad_address") else "network"
        reason = info["reason_zh"] if kind == info["kind"] else errors.NETWORK
        logger.info("voice key check %s: %s", provider_id, type(exc).__name__)
        return {"ok": False, "kind": kind, "reason_zh": reason}
    finally:
        key = ""
        if own:
            c.close()
    code = int(getattr(resp, "status_code", 0) or 0)
    logger.info("voice key check %s: HTTP %s", provider_id, code)
    if 200 <= code < 300:
        return {"ok": True, "kind": "ok", "reason_zh": "连接正常"}
    if code in (401, 403):
        return {"ok": False, "kind": "auth", "reason_zh": errors.AUTH}
    if code == 402:
        return {"ok": False, "kind": "balance", "reason_zh": errors.BALANCE}
    if code == 429:
        return {"ok": False, "kind": "rate_limit", "reason_zh": errors.RATE_LIMIT}
    return {"ok": False, "kind": "http", "reason_zh": f"验证 Key 出错（HTTP {code}）"}
