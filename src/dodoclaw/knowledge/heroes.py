"""Build hero mechanism documents from OpenDota constants."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from dodoclaw.knowledge.util import pretty_hero_key, strip_html

logger = logging.getLogger(__name__)

OPENDOTA = "https://api.opendota.com/api"


def _get_json(path: str, timeout: float = 90.0) -> Any:
    url = f"{OPENDOTA}{path}"
    with httpx.Client(timeout=timeout, headers={"User-Agent": "DoDoClaw-knowledge/0.4"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def _fmt_attrib(attrib: list[dict[str, Any]] | None) -> str:
    if not attrib:
        return ""
    bits: list[str] = []
    for a in attrib[:12]:
        header = strip_html(str(a.get("header") or a.get("key") or ""))
        val = a.get("value")
        if isinstance(val, list):
            val_s = "/".join(str(x) for x in val)
        else:
            val_s = str(val) if val is not None else ""
        if header and val_s:
            bits.append(f"{header.rstrip(':')} {val_s}")
    return "; ".join(bits)


def build_hero_documents() -> list[dict[str, Any]]:
    """
    Returns list of {id, title, kind, text, tags, hero_id, hero_key}.
    """
    heroes = _get_json("/constants/heroes")
    abilities = _get_json("/constants/abilities")
    try:
        hero_abilities = _get_json("/constants/hero_abilities")
    except Exception:
        logger.exception("hero_abilities fetch failed")
        hero_abilities = {}

    # heroes may be dict keyed by id string
    if isinstance(heroes, dict):
        hero_list = list(heroes.values())
    else:
        hero_list = list(heroes)

    docs: list[dict[str, Any]] = []
    for h in hero_list:
        if not isinstance(h, dict):
            continue
        hid = int(h.get("id") or 0)
        key = str(h.get("name") or "")
        if not key.startswith("npc_dota_hero_"):
            continue
        loc = str(h.get("localized_name") or pretty_hero_key(key))
        roles = h.get("roles") or []
        attr = h.get("primary_attr") or ""
        atk = h.get("attack_type") or ""

        lines = [
            f"英雄: {loc} ({key})",
            f"主属性: {attr}  攻击: {atk}",
            f"定位: {', '.join(roles) if roles else '—'}",
            f"移速: {h.get('move_speed')}  攻速相关 BAT: {h.get('base_attack_time')}",
            f"基础力量/敏捷/智力: {h.get('base_str')}/{h.get('base_agi')}/{h.get('base_int')}",
            f"成长: {h.get('str_gain')}/{h.get('agi_gain')}/{h.get('int_gain')}",
            "",
            "技能机制:",
        ]

        ab_names: list[str] = []
        ha = hero_abilities.get(key) if isinstance(hero_abilities, dict) else None
        if isinstance(ha, dict):
            raw_abs = ha.get("abilities") or []
            for item in raw_abs:
                if isinstance(item, str):
                    ab_names.append(item)
                elif isinstance(item, list):
                    ab_names.extend(str(x) for x in item if isinstance(x, str))
                elif item is not None:
                    ab_names.append(str(item))
        if not ab_names:
            # fallback: abilities that start with hero short name
            short = key.replace("npc_dota_hero_", "")
            ab_names = [
                n
                for n in (abilities.keys() if isinstance(abilities, dict) else [])
                if isinstance(n, str)
                and n.startswith(short + "_")
                and "special_bonus" not in n
            ][:6]

        skip_names = {"generic_hidden", "special_bonus_attributes"}
        for aname in ab_names:
            if not isinstance(aname, str) or aname in skip_names:
                continue
            a = abilities.get(aname) if isinstance(abilities, dict) else None
            if not isinstance(a, dict):
                lines.append(f"- {aname}")
                continue
            dname = strip_html(str(a.get("dname") or aname))
            desc = strip_html(str(a.get("desc") or ""))
            cd = a.get("cd")
            mc = a.get("mc")
            if isinstance(cd, list):
                cd_s = "/".join(str(x) for x in cd)
            else:
                cd_s = str(cd) if cd is not None else "—"
            if isinstance(mc, list):
                mc_s = "/".join(str(x) for x in mc)
            else:
                mc_s = str(mc) if mc is not None else "—"
            attrib_s = _fmt_attrib(a.get("attrib"))
            lines.append(f"- {dname} ({aname})")
            if desc:
                lines.append(f"  说明: {desc}")
            lines.append(f"  CD: {cd_s}  魔法: {mc_s}")
            if attrib_s:
                lines.append(f"  数值: {attrib_s}")

        text = "\n".join(lines)
        tags = [loc.lower(), key.lower(), pretty_hero_key(key).lower(), "hero", "ability"]
        if isinstance(roles, list):
            tags.extend(str(r).lower() for r in roles if not isinstance(r, (list, dict)))
        docs.append(
            {
                "id": f"hero:{key}",
                "kind": "hero",
                "title": f"{loc} 技能与机制",
                "text": text,
                "tags": tags,
                "hero_id": hid,
                "hero_key": key,
                "localized_name": loc,
            }
        )
    logger.info("built %s hero mechanism docs", len(docs))
    return docs
