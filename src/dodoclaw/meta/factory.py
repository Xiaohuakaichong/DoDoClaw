"""Create meta provider from settings (OpenDota | STRATZ)."""

from __future__ import annotations

import logging
from typing import Any

from dodoclaw.meta.opendota import OpenDotaClient

logger = logging.getLogger(__name__)


def create_meta_provider(
    source: str = "opendota",
    *,
    opendota_api_key: str = "",
    stratz_api_token: str = "",
    cache_ttl_sec: int = 6 * 3600,
    opendota_bracket: int = 0,
    stratz_bracket: str = "high",
    fallback_opendota: bool = True,
) -> Any:
    """
    source: opendota | stratz | auto
    auto: prefer STRATZ if token present, else OpenDota
    """
    src = (source or "opendota").strip().lower()
    if src == "auto":
        src = "stratz" if stratz_api_token.strip() else "opendota"

    if src == "stratz":
        try:
            from dodoclaw.meta.stratz import StratzClient

            return StratzClient(
                api_token=stratz_api_token,
                cache_ttl_sec=cache_ttl_sec,
                bracket=stratz_bracket,
            )
        except Exception as exc:
            logger.warning("STRATZ init failed (%s); fallback=%s", exc, fallback_opendota)
            if not fallback_opendota:
                raise
            return OpenDotaClient(
                api_key=opendota_api_key,
                cache_ttl_sec=cache_ttl_sec,
                bracket=opendota_bracket,
            )

    return OpenDotaClient(
        api_key=opendota_api_key,
        cache_ttl_sec=cache_ttl_sec,
        bracket=opendota_bracket,
    )
