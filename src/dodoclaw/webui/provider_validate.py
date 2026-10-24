"""Validate OpenAI-compatible base URL and model ID for the settings page.

Errors are fixed Chinese strings only — never echo the user's input back in a
way that could leak a key, and never raise with the raw value.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

MSG_URL_EMPTY = "请填写接口地址"
MSG_URL_SCHEME = "接口地址必须以 http:// 或 https:// 开头"
MSG_URL_HOST = "接口地址缺少主机名"
MSG_URL_HTTP_PUBLIC = "非本机地址请用 https://（http 只允许 localhost 和局域网）"
MSG_URL_BAD = "接口地址格式不对"
# Valid-shaped URL but the probe could not reach it (DNS / refused / timeout)
MSG_URL_UNREACHABLE = "接口地址连不上 · 检查地址或网络后重试"
MSG_MODEL_EMPTY = "请填写模型 ID"
MSG_MODEL_LONG = "模型 ID 最多 200 个字符"
MSG_MODEL_SPACE = "模型 ID 不能有空格或换行"

_TRAIL_CHAT = re.compile(r"/chat/completions/?$", re.I)
_WS = re.compile(r"\s")


def _is_private_or_loopback(host: str) -> bool:
    h = (host or "").strip().lower().rstrip(".")
    if h in {"localhost", "localhost.localdomain"}:
        return True
    # strip IPv6 brackets
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        # hostname that is not an IP: only allow literal localhost forms above
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def normalize_base_url(raw: str) -> str:
    """Trim, strip a trailing /chat/completions, drop a trailing slash. Raises ValueError(zh)."""
    u = (raw or "").strip()
    if not u:
        raise ValueError(MSG_URL_EMPTY)
    u = _TRAIL_CHAT.sub("", u).rstrip("/")
    try:
        p = urlparse(u)
    except Exception as exc:
        raise ValueError(MSG_URL_BAD) from None
    scheme = (p.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError(MSG_URL_SCHEME)
    host = p.hostname or ""
    if not host:
        raise ValueError(MSG_URL_HOST)
    if scheme == "http" and not _is_private_or_loopback(host):
        raise ValueError(MSG_URL_HTTP_PUBLIC)
    # rebuild without fragment; keep path/query as given (minus chat/completions)
    path = p.path or ""
    if path == "/":
        path = ""
    netloc = p.netloc
    out = f"{scheme}://{netloc}{path}"
    if p.query:
        out += f"?{p.query}"
    return out.rstrip("/")


def validate_model_id(raw: str) -> str:
    """Trimmed model ID, or ValueError with a Chinese reason."""
    m = (raw or "").strip()
    if not m:
        raise ValueError(MSG_MODEL_EMPTY)
    if len(m) > 200:
        raise ValueError(MSG_MODEL_LONG)
    if _WS.search(m):
        raise ValueError(MSG_MODEL_SPACE)
    return m
