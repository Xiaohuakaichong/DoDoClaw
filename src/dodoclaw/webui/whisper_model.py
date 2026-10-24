"""First-use download of the local Whisper model (faster-whisper base, CPU int8).

Weights are NOT bundled; they download on first use with progress / cancel /
retry. All user-facing strings are Chinese. HuggingFace's default endpoint is
used — a third-party mirror (e.g. HF_ENDPOINT=https://hf-mirror.com) is
honoured if the user already set it in the environment, but we never set one
ourselves.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def component_available() -> bool:
    """True when the faster-whisper *package* is importable (weights may still be missing).

    PyInstaller onedir can make bare ``find_spec`` miss a collected package under
    ``sys._MEIPASS``; fall back to the MEIPASS folder and a real import.
    """
    import importlib
    import importlib.util
    import sys

    if importlib.util.find_spec("faster_whisper") is not None:
        return True
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", "") or "")
        if meipass.is_dir() and (meipass / "faster_whisper").is_dir():
            return True
        try:
            importlib.import_module("faster_whisper")
            return True
        except Exception:
            return False
    return False


MODEL_SIZE = "base"
# Official faster-whisper converted weights on Hugging Face
HF_REPO = "Systran/faster-whisper-base"
# Approximate total for progress UI (model.bin ~145 MB + tokenizer + vocab)
EXPECTED_BYTES = 148 << 20  # ~148 MB

MSG_MISSING = "缺少本地识别组件"
MSG_DOWNLOADING = "正在下载识别模型…"
MSG_READY = "本地模型已就绪"
MSG_FAIL = "模型下载失败，检查网络后重试"
MSG_CANCELLED = "已取消下载"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "phase": "idle",  # idle | checking | downloading | ready | error | cancelled
    "pct": 0,
    "bytes_done": 0,
    "bytes_total": EXPECTED_BYTES,
    "error_zh": "",
    "ready": False,
}
_cancel = threading.Event()
_thread: threading.Thread | None = None


def model_dir() -> Path:
    """Where huggingface_hub / faster-whisper cache the weights."""
    # Respect HF hub cache layout; faster-whisper uses huggingface_hub under the hood
    home = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if home:
        root = Path(home)
    else:
        from dodoclaw.paths import user_data_dir

        # Prefer a writable app-local cache next to portable data
        root = user_data_dir() / "hf-cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def hf_mirror_note() -> str:
    """Report whether a user-supplied HF mirror is in effect (never set one)."""
    ep = (os.environ.get("HF_ENDPOINT") or "").strip()
    if ep:
        return f"使用环境变量 HF_ENDPOINT={ep}"
    return "未设置 HF_ENDPOINT（走 Hugging Face 官方）；如需镜像可自行设置 HF_ENDPOINT=https://hf-mirror.com"


def _cached_bytes(root: Path) -> int:
    """Bytes of this repo already on disk, including in-flight ``*.incomplete`` blobs.

    huggingface_hub writes to ``blobs/<sha>.incomplete`` (hash names), so matching
    on ``model.bin`` alone kept the bar at 0% until the very end.
    """
    repo = root / ("models--" + HF_REPO.replace("/", "--"))
    done = 0
    try:
        for f in repo.rglob("*"):
            if f.is_file() and not f.is_symlink():
                done += f.stat().st_size
    except Exception:
        pass
    return done


def _snapshot_ready() -> bool:
    """True when the converted model files are present in the hub cache."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:
        # Fallback: look for model.bin under the cache tree
        cache = model_dir()
        return any(cache.rglob("model.bin"))
    # try_to_load_from_cache returns a path or None/_CACHED_NO_EXIST
    path = try_to_load_from_cache(HF_REPO, "model.bin", cache_dir=str(model_dir()))
    return isinstance(path, str) and Path(path).is_file()


def status() -> dict[str, Any]:
    with _lock:
        st = dict(_state)
    if st["phase"] in {"idle", "ready"} and _snapshot_ready():
        st["phase"] = "ready"
        st["ready"] = True
        st["pct"] = 100
    st["mirror_note"] = hf_mirror_note()
    st["model"] = MODEL_SIZE
    st["repo"] = HF_REPO
    return st


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def start_download() -> dict[str, Any]:
    """Kick off a background download if needed. Idempotent."""
    global _thread
    if _snapshot_ready():
        _set(phase="ready", ready=True, pct=100, error_zh="", bytes_done=EXPECTED_BYTES)
        return status()
    with _lock:
        if _thread is not None and _thread.is_alive():
            return status()
        _cancel.clear()
        _thread = threading.Thread(target=_download_worker, name="whisper-dl", daemon=True)
        _thread.start()
    return status()


def cancel_download() -> dict[str, Any]:
    _cancel.set()
    _set(phase="cancelled", error_zh=MSG_CANCELLED, ready=False)
    return status()


def ensure_ready(timeout: float = 600.0) -> bool:
    """Block until the model is cached (used by STT init). Returns False on fail/cancel."""
    if _snapshot_ready():
        _set(phase="ready", ready=True, pct=100)
        return True
    start_download()
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = status()
        if st["phase"] == "ready" and st["ready"]:
            return True
        if st["phase"] in {"error", "cancelled"}:
            return False
        time.sleep(0.25)
    return _snapshot_ready()


def _download_worker() -> None:
    _set(phase="downloading", pct=0, bytes_done=0, bytes_total=EXPECTED_BYTES, error_zh="", ready=False)
    # Point huggingface_hub at our cache without forcing a mirror
    os.environ.setdefault("HF_HOME", str(model_dir()))
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except Exception as exc:
        logger.warning("huggingface_hub missing: %s", type(exc).__name__)
        _set(phase="error", error_zh=MSG_FAIL, ready=False)
        return

    # Prefer snapshot_download with a tqdm-like callback via resume
    try:
        def _cb(progress: int, total: int) -> None:
            if _cancel.is_set():
                raise KeyboardInterrupt("cancelled")
            total = total or EXPECTED_BYTES
            pct = int(min(99, (progress / total) * 100)) if total else 0
            _set(phase="downloading", pct=pct, bytes_done=progress, bytes_total=total)

        # huggingface_hub >=0.23 supports max_workers; progress via tqdm disabled —
        # poll cache size instead while download runs in this thread.
        stop_poll = threading.Event()

        def _poll() -> None:
            root = model_dir()
            while not stop_poll.wait(0.4):
                if _cancel.is_set():
                    return
                done = _cached_bytes(root)
                total = max(EXPECTED_BYTES, done)
                pct = int(min(99, done / EXPECTED_BYTES * 100))
                _set(phase="downloading", pct=pct, bytes_done=done, bytes_total=EXPECTED_BYTES)

        poller = threading.Thread(target=_poll, daemon=True)
        poller.start()
        try:
            snapshot_download(
                repo_id=HF_REPO,
                cache_dir=str(model_dir()),
                local_files_only=False,
            )
        finally:
            stop_poll.set()
            poller.join(timeout=2)
        if _cancel.is_set():
            _set(phase="cancelled", error_zh=MSG_CANCELLED, ready=False)
            return
        if not _snapshot_ready():
            # Force the main weight file
            hf_hub_download(HF_REPO, "model.bin", cache_dir=str(model_dir()))
        _set(phase="ready", ready=True, pct=100, bytes_done=EXPECTED_BYTES, error_zh="")
    except KeyboardInterrupt:
        _set(phase="cancelled", error_zh=MSG_CANCELLED, ready=False)
    except Exception:
        logger.exception("whisper model download failed")
        _set(phase="error", error_zh=MSG_FAIL, ready=False)
