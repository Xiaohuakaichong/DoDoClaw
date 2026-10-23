from __future__ import annotations

import logging
from typing import Any

from dodoclaw.coach.prompts import DEFAULT_SYSTEM, build_user_message
from dodoclaw.providers import DEFAULT_PROVIDER_ID, chat_extra_body
from dodoclaw.gsi.state import GameSnapshot

logger = logging.getLogger(__name__)


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
        self.system_prompt = system_prompt or DEFAULT_SYSTEM
        self.max_reply_chars = max_reply_chars
        self.provider_id = provider_id
        self.provider_name = provider_name or provider_id
        self._client: Any = None

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
            from openai import OpenAI

            if not self.api_key:
                raise RuntimeError(
                    "未设置 API Key。请在界面选择 Provider 并保存 Key，"
                    "或在 .env 中设置 LLM_API_KEY / 对应厂商 Key。"
                )
            # timeout: connect 10s, total 60s — avoid silent hang on send
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0,
            )
        return self._client

    def answer(
        self,
        question: str,
        snapshot: GameSnapshot,
        draft_context: str = "",
        knowledge_context: str = "",
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
        )
        client = self._get_client()

        # Chat Completions: widest CN OpenAI-compatible coverage
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.55,
                max_tokens=500,
                extra_body=chat_extra_body(self.provider_id, self.model) or None,
            )
            text = (resp.choices[0].message.content or "").strip()
        except Exception:
            logger.exception(
                "chat.completions failed (provider=%s model=%s); trying responses API",
                self.provider_id,
                self.model,
            )
            try:
                resp = client.responses.create(
                    model=self.model,
                    input=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                )
                text = (getattr(resp, "output_text", None) or str(resp)).strip()
            except Exception as exc:
                msg = str(exc)
                hint = ""
                if "401" in msg or "invalid_api_key" in msg or "Incorrect API key" in msg:
                    hint = " → API Key 无效或未保存，请重新粘贴并点「保存 Provider 配置」。"
                elif "404" in msg or "model" in msg.lower():
                    hint = " → 检查模型名是否在该 Provider 下可用。"
                elif "timeout" in msg.lower() or "timed out" in msg.lower():
                    hint = " → 网络超时，检查代理 / Base URL。"
                raise RuntimeError(
                    f"LLM 调用失败 [{self.provider_name}] {self.base_url} "
                    f"model={self.model}: {exc}{hint}"
                ) from exc

        if self.max_reply_chars and len(text) > self.max_reply_chars:
            text = text[: self.max_reply_chars - 1].rstrip() + "…"
        return text

    def answer_offline_fallback(self, question: str, snapshot: GameSnapshot) -> str:
        """No-API fallback for smoke tests."""
        return (
            f"（离线模式）收到问题：{question}。"
            f" 当前时间 {snapshot.clock_mmss}，英雄 {snapshot.hero_name or '未知'}。"
            f" 请配置 Provider（当前倾向 {self.provider_name}）与 API Key 后启用完整教练回答。"
        )
