from __future__ import annotations

import logging
import re
import threading
from collections import deque
from typing import Any

from dodoclaw.coach.prompts import build_system_prompt, build_user_message
from dodoclaw.gsi.state import GameSnapshot
from dodoclaw.providers import (
    DEFAULT_PROVIDER_ID,
    chat_extra_body,
    chat_max_tokens,
    chat_temperature,
)

logger = logging.getLogger(__name__)

# A live coach answer that takes longer than this is useless anyway. The SDK
# default (600 s, 2 retries) plus the Responses fallback could hang ~6 minutes.
REQUEST_TIMEOUT_SEC = 60.0
CONNECT_TIMEOUT_SEC = 10.0
MAX_RETRIES = 1
# Only these mean "this endpoint doesn't speak Chat Completions" — worth one try
# on the Responses API. Auth / balance / rate-limit / network errors are not.
FALLBACK_STATUS = (404, 405)

HISTORY_TURNS = 3  # follow-ups ("那第二件呢") within the same match
HISTORY_CHARS = 300  # per stored question / answer

_SENTENCE_END = re.compile(r"[。！？!?；;\n]")


def clip_reply(text: str, limit: int) -> str:
    """Trim to ``limit`` chars, preferring to end on a full sentence."""
    text = (text or "").strip()
    if not limit or len(text) <= limit:
        return text
    head = text[: limit - 1]
    ends = [m.end() for m in _SENTENCE_END.finditer(head)]
    if ends and ends[-1] >= limit * 0.5:
        return head[: ends[-1]].rstrip()
    return head.rstrip() + "…"


def _status(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None


class CoachAgent:
    """LLM coach via any OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stepfun.com/step_plan/v1",
        model: str = "step-3.7-flash",
        system_prompt: str | None = None,
        max_reply_chars: int = 280,
        provider_id: str = DEFAULT_PROVIDER_ID,
        provider_name: str = "",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        # style (settings.yaml coach.system_style, or the default) + fixed rules
        self.system_prompt = build_system_prompt(system_prompt)
        self.max_reply_chars = max_reply_chars
        self.provider_id = provider_id
        self.provider_name = provider_name or provider_id
        self._client: Any = None
        self._history: deque[tuple[str, str]] = deque(maxlen=HISTORY_TURNS)
        self._history_match = ""
        self._history_lock = threading.Lock()

    def configure(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider_id: str | None = None,
        provider_name: str | None = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        if model is not None:
            self.model = model
        if provider_id is not None:
            self.provider_id = provider_id
        if provider_name is not None:
            self.provider_name = provider_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx
            from openai import OpenAI

            if not self.api_key:
                raise RuntimeError(
                    "未设置 API Key。请在设置页选择服务商并保存 Key，"
                    "或在 .env 中设置 LLM_API_KEY / 对应厂商 Key。"
                )
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(REQUEST_TIMEOUT_SEC, connect=CONNECT_TIMEOUT_SEC),
                max_retries=MAX_RETRIES,
            )
        return self._client

    # ── short per-match memory ──────────────────────────
    def reset_history(self) -> None:
        with self._history_lock:
            self._history.clear()

    def _history_messages(self, match_id: str) -> list[dict[str, str]]:
        with self._history_lock:
            if match_id != self._history_match:
                # new match (or left one): old follow-ups would only confuse
                self._history.clear()
                self._history_match = match_id
            msgs: list[dict[str, str]] = []
            for q, a in self._history:
                msgs.append({"role": "user", "content": f"【之前的对话】{q}"})
                msgs.append({"role": "assistant", "content": a})
            return msgs

    def _remember(self, match_id: str, question: str, answer: str) -> None:
        with self._history_lock:
            if match_id == self._history_match:
                self._history.append((question[:HISTORY_CHARS], answer[:HISTORY_CHARS]))

    def answer(
        self,
        question: str,
        snapshot: GameSnapshot,
        draft_context: str = "",
        knowledge_context: str = "",
        objectives_context: str = "",
        heroes_context: str = "",
    ) -> str:
        question = (question or "").strip()
        if not question:
            return ""

        context = snapshot.summary_for_llm()
        user_msg = build_user_message(
            question,
            context,
            draft_context=draft_context,
            knowledge_context=knowledge_context,
            objectives_context=objectives_context,
            heroes_context=heroes_context,
        )
        match_id = str(getattr(snapshot, "match_id", "") or "")
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self._history_messages(match_id),
            {"role": "user", "content": user_msg},
        ]
        client = self._get_client()

        # Chat Completions: widest CN OpenAI-compatible coverage
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=chat_temperature(self.provider_id, self.model, default=0.55),
                max_tokens=chat_max_tokens(self.provider_id, self.model, default=500),
                extra_body=chat_extra_body(self.provider_id, self.model) or None,
            )
            text = (resp.choices[0].message.content or "").strip()
        except Exception as chat_exc:
            if _status(chat_exc) not in FALLBACK_STATUS:
                logger.warning(
                    "chat.completions failed (provider=%s model=%s): %s",
                    self.provider_id,
                    self.model,
                    type(chat_exc).__name__,
                )
                raise RuntimeError(
                    f"LLM 调用失败 [{self.provider_name}] {self.base_url} model={self.model}"
                ) from chat_exc
            logger.warning(
                "chat.completions HTTP %s (provider=%s model=%s); trying responses API",
                _status(chat_exc),
                self.provider_id,
                self.model,
            )
            try:
                resp = client.responses.create(model=self.model, input=messages)
                text = (getattr(resp, "output_text", None) or "").strip()
            except Exception as exc:
                raise RuntimeError(
                    f"LLM 调用失败 [{self.provider_name}] {self.base_url} "
                    f"model={self.model} → 检查模型名是否在该服务商下可用"
                ) from exc

        text = clip_reply(text, self.max_reply_chars)
        if text:
            self._remember(match_id, question, text)
        return text

    def answer_offline_fallback(self, question: str, snapshot: GameSnapshot) -> str:
        """No-API fallback for smoke tests."""
        return (
            f"（离线模式）收到问题：{question}。"
            f" 当前时间 {snapshot.clock_mmss}，英雄 {snapshot.hero_name or '未知'}。"
            f" 请配置 Provider（当前倾向 {self.provider_name}）与 API Key 后启用完整教练回答。"
        )
