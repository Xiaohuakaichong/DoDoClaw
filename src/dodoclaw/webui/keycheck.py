"""API-key status for the settings page — booleans only, never the key itself.

Rules: nothing in this module returns, logs or prints a key value, and nothing
writes to ``.env``. ``reload_env`` only *reads* the file.
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
STT_PROVIDERS = {"stepfun_plan", "stepfun"}


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


def key_status(provider_id: str, provider_name: str, api_key: str) -> dict[str, Any]:
    spec = get_provider(provider_id)
    flags = env_flags()
    return {
        "configured": bool((api_key or "").strip()),
        "source": "env",
        "provider": spec.id,
        "provider_name": provider_name or spec.name,
        "key_env": spec.key_env,
        "docs": bool(spec.docs_url),
        "has_stt": spec.id in STT_PROVIDERS,
        "stepfun_key": flags.get("STEPFUN_API_KEY", False)
        or (spec.id in STT_PROVIDERS and bool((api_key or "").strip())),
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
