"""Where coach API keys are stored (PRD D10).

Storage sits behind one small ``KeyStore`` interface (get / set / has / delete)
because Windows 凭据管理器 vs ``.env`` is still undecided; the settings page,
``js_api`` and the wording are the same either way. Only the ``.env`` backend
exists and is wired. Keys a user typed into ``.env`` by hand keep working: the
app still reads keys through ``.env`` → ``os.environ`` as before.

Safety rules: nothing here logs a key or puts one into an exception message;
errors carry a fixed Chinese reason only. ``get`` is for Python callers — the
settings bridge never returns a key to JS.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from dodoclaw.providers import PROVIDERS

# Only key variables may be written from the settings page.
# Custom providers use CUSTOM_<ID>_API_KEY (see webui.customs).
_BASE_ALLOWED: frozenset[str] = frozenset({p.key_env for p in PROVIDERS.values()} | {"LLM_API_KEY"})
ALLOWED_VARS: frozenset[str] = _BASE_ALLOWED  # kept for tests / imports; use allowed() for checks

MSG_EMPTY = "Key 是空的，先粘贴进来"
MSG_NEWLINE = "Key 里有换行，只粘贴一行"
MSG_BAD_CHARS = "Key 里有空格、引号或其他特殊字符，检查是不是复制多了"
MSG_TOO_LONG = "Key 太长了，检查是不是复制多了"
MSG_BAD_VAR = "这个服务商不能在这里保存 Key"
MSG_WRITE = "没能写入 .env，检查文件是不是只读，详情见日志"

# printable ASCII without space, quotes and backslash
_OK_CHARS = re.compile(r"^[\x21\x23-\x26\x28-\x5b\x5d-\x7e]+$")
_NEEDS_QUOTES = re.compile(r"[#$]")  # comment / interpolation in python-dotenv


class KeyStoreError(ValueError):
    """Carries a Chinese reason only — never the key."""

    def __init__(self, reason_zh: str) -> None:
        super().__init__(reason_zh)
        self.reason_zh = reason_zh


def clean_key(value: str) -> str:
    """Trimmed key, or KeyStoreError with a Chinese reason."""
    v = (value or "").strip()
    if not v:
        raise KeyStoreError(MSG_EMPTY)
    if "\n" in v or "\r" in v:
        raise KeyStoreError(MSG_NEWLINE)
    if len(v) > 512:
        raise KeyStoreError(MSG_TOO_LONG)
    if not _OK_CHARS.match(v):
        raise KeyStoreError(MSG_BAD_CHARS)
    return v


class KeyStore(Protocol):
    """Key storage, addressed by the provider's env var name (e.g. DEEPSEEK_API_KEY)."""

    def get(self, env_var: str) -> str: ...
    def set(self, env_var: str, value: str) -> None: ...
    def has(self, env_var: str) -> bool: ...
    def delete(self, env_var: str) -> None: ...


def env_path() -> Path:
    """The .env the app reads: next to the exe, or the repo root from source."""
    from dodoclaw.paths import app_dir

    return app_dir() / ".env"


def _assign_re(var: str) -> re.Pattern[str]:
    return re.compile(r"^\s*(?:export\s+)?" + re.escape(var) + r"\s*=")


def upsert_env_line(path: Path, var: str, value: str | None) -> None:
    """Set ``var=value`` in a .env file.

    - creates the file if missing;
    - replaces every active ``var=`` line in place (python-dotenv takes the
      last one, so duplicates are updated too); commented lines are left alone;
    - otherwise appends one line at the end;
    - every other line, comment, blank line and the order are kept byte-for-byte,
      including CRLF line endings;
    - ``value=None`` removes the active ``var=`` lines instead;
    - writes UTF-8 without BOM, atomically (temp file + rename); no backup copy
      is kept, so old keys never linger in a second plaintext file.
    """
    raw = path.read_bytes() if path.exists() else b""
    text = raw.decode("utf-8-sig")  # drops a BOM if a text editor added one
    nl = "\r\n" if "\r\n" in text else "\n"
    new_line = ""
    if value is not None:
        rendered = f"'{value}'" if _NEEDS_QUOTES.search(value) else value
        new_line = f"{var}={rendered}"

    lines = text.splitlines(keepends=True)
    pat = _assign_re(var)
    found = False
    for i, ln in enumerate(lines):
        if pat.match(ln):
            ending = ln[len(ln.rstrip("\r\n")):]
            lines[i] = new_line + ending if value is not None else ""
            found = True
    if not found and value is not None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        lines.append(new_line + nl)
    data = "".join(lines).encode("utf-8")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class EnvFileKeyStore:
    """Keys as ``VAR=value`` lines in the portable .env next to the exe."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or env_path()

    def _write(self, env_var: str, value: str | None) -> None:
        try:
            upsert_env_line(self.path, env_var, value)
        except OSError as exc:
            # class + errno only, and no exception chaining
            import logging

            logging.getLogger(__name__).warning("key store write failed: %s errno=%s", type(exc).__name__, exc.errno)
            raise KeyStoreError(MSG_WRITE) from None

    def get(self, env_var: str) -> str:
        env = (os.environ.get(env_var) or "").strip()
        if env:
            return env
        p = self.path
        if not p.exists():
            return ""
        from dotenv import dotenv_values

        return (dotenv_values(p).get(env_var) or "").strip()

    def set(self, env_var: str, value: str) -> None:
        self._write(env_var, value)

    def has(self, env_var: str) -> bool:
        return bool(self.get(env_var))

    def delete(self, env_var: str) -> None:
        # 更换 Key → 删除 Key: only the active ``var=`` lines go; comments stay
        self._write(env_var, None)
        os.environ.pop(env_var, None)


_store: KeyStore = EnvFileKeyStore()


def store() -> KeyStore:
    return _store


def allowed(env_var: str) -> bool:
    from dodoclaw.webui.customs import is_custom_key_env

    return env_var in _BASE_ALLOWED or is_custom_key_env(env_var)


def save_key(env_var: str, value: str) -> None:
    """Validate and store a key. Raises KeyStoreError (Chinese reason, no key)."""
    if not allowed(env_var):
        raise KeyStoreError(MSG_BAD_VAR)
    _store.set(env_var, clean_key(value))


def delete_key(env_var: str) -> None:
    """Remove a stored key. Raises KeyStoreError (Chinese reason only)."""
    if not allowed(env_var):
        raise KeyStoreError(MSG_BAD_VAR)
    _store.delete(env_var)


def has_key(env_var: str) -> bool:
    return bool(env_var) and _store.has(env_var)
