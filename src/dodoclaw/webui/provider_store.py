"""Non-secret, per-preset connection settings for the Provider Hub.

The coach selection remains in ``coach``. Saving a provider here never selects
it. Existing ``coach.base_url`` / ``coach.model`` are read until that preset has
its own entry, so upgrading keeps the user's working connection intact.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from dodoclaw.providers import DEFAULT_PROVIDER_ID, PROVIDERS, get_provider


def settings_path() -> Path:
    from dodoclaw.config import config_dir

    return config_dir() / "settings.yaml"


def load(path: Path | None = None) -> dict[str, Any]:
    p = path or settings_path()
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def preset_values(provider_id: str, data: dict[str, Any] | None = None) -> dict[str, str]:
    """Return URL/model, including the current coach's legacy overrides."""
    spec = get_provider(provider_id)
    data = load() if data is None else data
    entries = data.get("provider_configs") or {}
    entry = entries.get(spec.id) if isinstance(entries, dict) else None
    if not isinstance(entry, dict):
        coach = data.get("coach") or {}
        entry = coach if isinstance(coach, dict) and get_provider(
            str(coach.get("provider") or DEFAULT_PROVIDER_ID)
        ).id == spec.id and str(coach.get("provider") or "") != "custom" else {}
    return {
        "base_url": str(entry.get("base_url") or spec.base_url).strip().rstrip("/"),
        "model": str(entry.get("model") or spec.default_model).strip(),
    }


def _entries(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = data.get("provider_configs") or {}
    entries = {
        pid: preset_values(pid, {"provider_configs": {pid: entry}})
        for pid, entry in (raw.items() if isinstance(raw, dict) else [])
        if pid in PROVIDERS and pid != "custom" and isinstance(entry, dict)
    }
    # Migrate the active legacy preset before another choice can replace it.
    coach = data.get("coach") or {}
    if isinstance(coach, dict):
        pid = get_provider(str(coach.get("provider") or DEFAULT_PROVIDER_ID)).id
        if pid in PROVIDERS and pid != "custom" and pid not in entries:
            entries[pid] = preset_values(pid, data)
    return entries


def _write(path: Path, entries: dict[str, dict[str, str]]) -> None:
    """Replace only our top-level YAML section; retain unrelated comments."""
    from dodoclaw.config import reload_settings, replace_settings_file

    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^provider_configs\s*:", line)), None)
    section = yaml.safe_dump(
        {"provider_configs": entries}, allow_unicode=True, sort_keys=False
    ).rstrip().splitlines()
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(section)
    else:
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][:1] in (" ", "\t")):
            end += 1
        lines[start:end] = section + [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    replace_settings_file(tmp, path)
    reload_settings()


def remember_active(path: Path | None = None) -> None:
    path = path or settings_path()
    data = load(path)
    _write(path, _entries(data))


def save_preset(provider_id: str, base_url: str, model: str, path: Path | None = None) -> None:
    from dodoclaw.webui.provider_validate import normalize_base_url, validate_model_id

    if provider_id not in PROVIDERS or provider_id == "custom":
        raise ValueError("没有这个服务商")
    values = {"base_url": normalize_base_url(base_url), "model": validate_model_id(model)}
    path = path or settings_path()
    entries = _entries(load(path))
    entries[provider_id] = values
    _write(path, entries)
