"""Fetch official Dota 2 patch notes (Valve datafeed)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from dodoclaw.knowledge.util import strip_html

logger = logging.getLogger(__name__)

PATCH_LIST = "https://www.dota2.com/datafeed/patchnoteslist"
PATCH_DETAIL = "https://www.dota2.com/datafeed/patchnotes"
# language: schinese | english | ...
DEFAULT_LANG = "schinese"


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=60.0,
        headers={"User-Agent": "DoDoClaw-knowledge/0.4"},
    )


def list_patches(language: str = DEFAULT_LANG) -> list[dict[str, Any]]:
    with _client() as c:
        r = c.get(PATCH_LIST, params={"language": language})
        r.raise_for_status()
        data = r.json()
    return list(data.get("patches") or [])


def fetch_patch(version: str, language: str = DEFAULT_LANG) -> dict[str, Any]:
    with _client() as c:
        r = c.get(PATCH_DETAIL, params={"language": language, "version": version})
        r.raise_for_status()
        return r.json()


def _notes_from_generic(items: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for it in items or []:
        note = strip_html(str(it.get("note") or ""))
        if note and note not in {"", "<br>"}:
            out.append(note)
    return out


def patch_to_documents(
    patch: dict[str, Any],
    *,
    heroes_by_id: dict[int, dict[str, Any]] | None = None,
    ability_id_to_name: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Flatten one patch JSON into searchable documents."""
    ver = str(patch.get("patch_number") or patch.get("patch_name") or "unknown")
    docs: list[dict[str, Any]] = []
    heroes_by_id = heroes_by_id or {}
    ability_id_to_name = ability_id_to_name or {}

    # General notes
    general_lines: list[str] = [f"补丁 {ver} · 全局改动"]
    for block in patch.get("general_notes") or []:
        title = strip_html(str(block.get("title") or "通用"))
        general_lines.append(f"## {title}")
        for n in _notes_from_generic(block.get("generic")):
            general_lines.append(f"- {n}")
    if len(general_lines) > 1:
        docs.append(
            {
                "id": f"patch:{ver}:general",
                "kind": "patch_general",
                "title": f"补丁 {ver} 全局",
                "text": "\n".join(general_lines),
                "tags": ["patch", ver, "general", "全局", "版本"],
                "patch": ver,
            }
        )

    # Items
    item_lines = [f"补丁 {ver} · 物品改动"]
    for block in patch.get("items") or []:
        # structure varies; try common fields
        name = strip_html(str(block.get("title") or block.get("name") or "item"))
        notes = _notes_from_generic(block.get("generic") or block.get("notes"))
        if not notes and block.get("note"):
            notes = [strip_html(str(block.get("note")))]
        if notes:
            item_lines.append(f"## {name}")
            item_lines.extend(f"- {n}" for n in notes)
    if len(item_lines) > 1:
        docs.append(
            {
                "id": f"patch:{ver}:items",
                "kind": "patch_items",
                "title": f"补丁 {ver} 物品",
                "text": "\n".join(item_lines),
                "tags": ["patch", ver, "item", "物品"],
                "patch": ver,
            }
        )

    # Heroes
    for hblock in patch.get("heroes") or []:
        hid = int(hblock.get("hero_id") or 0)
        hinfo = heroes_by_id.get(hid) or {}
        hkey = str(hinfo.get("name") or f"hero_{hid}")
        hloc = str(hinfo.get("localized_name") or hkey)
        lines = [f"补丁 {ver} · 英雄 {hloc} ({hkey})"]
        for n in _notes_from_generic(hblock.get("hero_notes")):
            lines.append(f"- 英雄本体: {n}")
        for ab in hblock.get("abilities") or []:
            aid = int(ab.get("ability_id") or 0)
            aname = ability_id_to_name.get(aid) or f"ability_{aid}"
            ab_notes = _notes_from_generic(ab.get("ability_notes"))
            if ab_notes:
                lines.append(f"- 技能 {aname}:")
                lines.extend(f"  · {n}" for n in ab_notes)
        if len(lines) <= 1:
            continue
        tags = [
            "patch",
            ver,
            "hero",
            hloc.lower(),
            hkey.lower(),
            hkey.replace("npc_dota_hero_", "").lower(),
        ]
        docs.append(
            {
                "id": f"patch:{ver}:hero:{hid}",
                "kind": "patch_hero",
                "title": f"补丁 {ver} · {hloc}",
                "text": "\n".join(lines),
                "tags": tags,
                "patch": ver,
                "hero_id": hid,
                "hero_key": hkey,
                "localized_name": hloc,
            }
        )

    logger.info("patch %s -> %s docs", ver, len(docs))
    return docs


def build_recent_patch_documents(
    *,
    language: str = DEFAULT_LANG,
    last_n: int = 3,
    heroes_by_id: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    patches = list_patches(language=language)
    if not patches:
        return []
    # ability id map
    ability_id_to_name: dict[int, str] = {}
    try:
        with _client() as c:
            r = c.get("https://api.opendota.com/api/constants/ability_ids")
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        try:
                            ability_id_to_name[int(k)] = str(v)
                        except ValueError:
                            pass
    except Exception:
        logger.debug("ability_ids map failed", exc_info=True)

    if heroes_by_id is None:
        heroes_by_id = {}
        try:
            with _client() as c:
                r = c.get("https://api.opendota.com/api/constants/heroes")
                r.raise_for_status()
                data = r.json()
            vals = data.values() if isinstance(data, dict) else data
            for h in vals:
                if isinstance(h, dict) and h.get("id") is not None:
                    heroes_by_id[int(h["id"])] = h
        except Exception:
            logger.exception("heroes map for patches failed")

    docs: list[dict[str, Any]] = []
    for p in patches[-last_n:]:
        ver = str(p.get("patch_number") or p.get("patch_name"))
        try:
            detail = fetch_patch(ver, language=language)
            docs.extend(
                patch_to_documents(
                    detail,
                    heroes_by_id=heroes_by_id,
                    ability_id_to_name=ability_id_to_name,
                )
            )
        except Exception:
            logger.exception("fetch patch %s failed", ver)
            # try english fallback once
            if language != "english":
                try:
                    detail = fetch_patch(ver, language="english")
                    docs.extend(
                        patch_to_documents(
                            detail,
                            heroes_by_id=heroes_by_id,
                            ability_id_to_name=ability_id_to_name,
                        )
                    )
                except Exception:
                    logger.exception("english fallback failed for %s", ver)
    return docs
