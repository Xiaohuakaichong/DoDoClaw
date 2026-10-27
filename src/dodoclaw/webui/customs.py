"""Custom OpenAI-compatible coach providers (PRD D12).

List lives in ``config/settings.yaml`` under ``coach.custom_providers``; the
active one is ``coach.provider: custom`` plus ``coach.custom_id``. Each entry's
Key is stored as ``CUSTOM_<ID>_API_KEY`` in ``.env`` (never returned to JS).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from dodoclaw.paths import config_dir
from dodoclaw.webui.provider_validate import normalize_base_url, validate_model_id

MSG_NOT_FOUND = "没有这家自定义服务商"
MSG_NAME_LONG = "名称最多 40 个字符"
_ID_RE = re.compile(r"^[a-z0-9]{4,12}$")
_NAME_MAX = 40


@dataclass(frozen=True)
class CustomProvider:
    id: str
    name: str
    base_url: str
    model: str

    @property
    def key_env(self) -> str:
        return f"CUSTOM_{self.id.upper()}_API_KEY"

    @property
    def display_name(self) -> str:
        return self.name or "自定义接口"

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "base_url": self.base_url, "model": self.model}


def key_env_for(custom_id: str) -> str:
    return f"CUSTOM_{(custom_id or '').upper()}_API_KEY"


def is_custom_key_env(var: str) -> bool:
    return bool(re.fullmatch(r"CUSTOM_[A-Z0-9]{4,12}_API_KEY", var or ""))


def _new_id(existing: set[str]) -> str:
    for _ in range(20):
        cid = uuid4().hex[:8]
        if cid not in existing and _ID_RE.match(cid):
            return cid
    raise RuntimeError("could not allocate custom provider id")


def _settings_path() -> Path:
    return config_dir() / "settings.yaml"


def _load_yaml(path: Path | None = None) -> dict[str, Any]:
    p = path or _settings_path()
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def list_customs(path: Path | None = None) -> list[CustomProvider]:
    coach = (_load_yaml(path).get("coach") or {}) if True else {}
    raw = coach.get("custom_providers") if isinstance(coach, dict) else None
    out: list[CustomProvider] = []
    if not isinstance(raw, list):
        return out
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or "").strip().lower()
        if not _ID_RE.match(cid) or cid in seen:
            continue
        try:
            url = normalize_base_url(str(item.get("base_url") or ""))
            model = validate_model_id(str(item.get("model") or ""))
        except ValueError:
            continue
        name = str(item.get("name") or "").strip()[:_NAME_MAX]
        seen.add(cid)
        out.append(CustomProvider(id=cid, name=name, base_url=url, model=model))
    return out


def get_custom(custom_id: str, path: Path | None = None) -> CustomProvider | None:
    cid = (custom_id or "").strip().lower()
    for c in list_customs(path):
        if c.id == cid:
            return c
    return None


def active_custom_id(path: Path | None = None) -> str:
    coach = _load_yaml(path).get("coach") or {}
    if not isinstance(coach, dict):
        return ""
    return str(coach.get("custom_id") or "").strip().lower()


def _dump_list(entries: list[CustomProvider]) -> list[dict[str, str]]:
    return [e.as_dict() for e in entries]


def _rewrite_custom_block(
    path: Path,
    entries: list[CustomProvider],
    *,
    custom_id: str | None = None,
    set_provider_custom: bool = False,
) -> None:
    """Rewrite coach.custom_providers (and optionally custom_id / provider) preserving other lines.

    Falls back to a full YAML dump of the coach block keys we own when the file
    has no coach section yet. Comments on unrelated keys are kept via line rewrite
    for provider/model/base_url/custom_id; the list itself is dumped as YAML.
    """
    from dodoclaw.config import reload_settings, replace_settings_file

    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r"^coach\s*:", ln)), None)
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("coach:")
        start = len(lines) - 1
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
        end += 1
    block = lines[start + 1 : end]

    # Drop existing custom_providers nested block and custom_id / provider lines we rewrite
    out: list[str] = []
    i = 0
    while i < len(block):
        ln = block[i]
        m = re.match(r"^(\s+)(custom_providers|custom_id|provider|model|base_url)\s*:", ln)
        if m and m.group(2) == "custom_providers":
            indent = len(m.group(1))
            i += 1
            while i < len(block):
                nxt = block[i]
                if not nxt.strip():
                    i += 1
                    continue
                lead = len(nxt) - len(nxt.lstrip(" \t"))
                if lead <= indent and re.match(r"^\s+\S", nxt):
                    # still nested if deeper; stop when indent <= custom_providers indent and looks like a key
                    if lead <= indent:
                        break
                if lead <= indent and re.match(r"^\s+[a-zA-Z_]", nxt):
                    break
                i += 1
            continue
        if m and (
            (m.group(2) == "custom_id" and custom_id is not None)
            or (set_provider_custom and m.group(2) in {"provider", "model", "base_url"})
        ):
            i += 1
            continue
        out.append(ln)
        i += 1

    list_yaml = yaml.safe_dump(
        _dump_list(entries),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip()
    # indent list under custom_providers
    list_lines = [f"  custom_providers:"]
    if entries:
        for ln in list_yaml.splitlines():
            list_lines.append("  " + ln if ln.startswith("-") or ln.startswith(" ") else "    " + ln)
        # yaml.safe_dump of a list starts with "- "; nest under key:
        list_lines = ["  custom_providers:"]
        for ln in list_yaml.splitlines():
            list_lines.append("    " + ln)
    else:
        list_lines = ["  custom_providers: []"]

    head: list[str] = []
    if set_provider_custom and entries:
        active = (custom_id or entries[0].id).strip().lower()
        cp = next((e for e in entries if e.id == active), entries[0])
        head.append('  provider: "custom"')
        head.append(f'  custom_id: "{cp.id}"')
        head.append(f'  model: {json.dumps(cp.model, ensure_ascii=False)}')
        head.append(f'  base_url: {json.dumps(cp.base_url, ensure_ascii=False)}')
    elif custom_id is not None:
        if custom_id:
            head.append(f'  custom_id: "{custom_id}"')
        # else: omit custom_id (cleared)

    new_block = head + list_lines + out
    lines[start + 1 : end] = new_block
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    replace_settings_file(tmp, path)
    reload_settings()


def save_custom(
    *,
    name: str = "",
    base_url: str,
    model: str,
    custom_id: str = "",
    path: Path | None = None,
    activate: bool = True,
) -> CustomProvider:
    """Create or update a custom provider. Validates URL/model. Returns the entry."""
    path = path or _settings_path()
    url = normalize_base_url(base_url)
    mdl = validate_model_id(model)
    nm = (name or "").strip()
    if len(nm) > _NAME_MAX:
        raise ValueError(MSG_NAME_LONG)
    entries = list_customs(path)
    by_id = {e.id: e for e in entries}
    cid = (custom_id or "").strip().lower()
    if cid:
        if cid not in by_id:
            raise ValueError(MSG_NOT_FOUND)
        entry = CustomProvider(id=cid, name=nm, base_url=url, model=mdl)
        entries = [entry if e.id == cid else e for e in entries]
    else:
        cid = _new_id(set(by_id))
        entry = CustomProvider(id=cid, name=nm, base_url=url, model=mdl)
        entries.append(entry)
    if activate:
        from dodoclaw.webui import provider_store

        provider_store.remember_active(path)
    _rewrite_custom_block(
        path,
        entries,
        custom_id=entry.id if activate else active_custom_id(path),
        set_provider_custom=activate,
    )
    return entry


def delete_custom(custom_id: str, path: Path | None = None) -> CustomProvider | None:
    """Remove a custom provider. Returns the removed entry (for key cleanup), or None."""
    path = path or _settings_path()
    cid = (custom_id or "").strip().lower()
    entries = list_customs(path)
    removed = next((e for e in entries if e.id == cid), None)
    if not removed:
        return None
    left = [e for e in entries if e.id != cid]
    cur = active_custom_id(path)
    coach = _load_yaml(path).get("coach") or {}
    was_active = isinstance(coach, dict) and coach.get("provider") == "custom" and cur == cid
    activate = bool(left) and was_active
    new_active = left[0].id if activate else (cur if cur != cid else "")
    _rewrite_custom_block(
        path,
        left,
        custom_id=new_active if left else "",
        set_provider_custom=activate,
    )
    if not left and was_active:
        # clear coach overrides back toward defaults without inventing a provider
        from dodoclaw import config

        data = _load_yaml(path)
        coach = data.get("coach") if isinstance(data, dict) else None
        if isinstance(coach, dict) and str(coach.get("provider") or "") == "custom":
            from dodoclaw.webui import provider_store

            values = provider_store.preset_values("deepseek", data)
            config.save_coach_choice("deepseek", values["model"], values["base_url"])
    return removed


def select_custom(custom_id: str, path: Path | None = None) -> CustomProvider:
    path = path or _settings_path()
    entry = get_custom(custom_id, path)
    if not entry:
        raise ValueError(MSG_NOT_FOUND)
    from dodoclaw.webui import provider_store

    provider_store.remember_active(path)
    entries = list_customs(path)
    _rewrite_custom_block(path, entries, custom_id=entry.id, set_provider_custom=True)
    return entry


def public_list(path: Path | None = None, *, current_id: str = "") -> list[dict[str, Any]]:
    """Booleans only — never keys. For the settings page list."""
    from dodoclaw.webui import keystore

    cur = (current_id or active_custom_id(path)).strip().lower()
    out = []
    for e in list_customs(path):
        out.append({
            "id": e.id,
            "name": e.display_name,
            "base_url": e.base_url,
            "model": e.model,
            "configured": keystore.has_key(e.key_env),
            "current": e.id == cur,
            "key_env": e.key_env,
        })
    return out
