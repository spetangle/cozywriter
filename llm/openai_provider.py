"""OpenAI (GPT) Provider"""
import time
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
from openai import OpenAI


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "gpt-4o"):
        self.api_key = api_key or settings.openai_api_key
        self.model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        task_type = kwargs.get("task_type", "generate")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # 记录完整 prompt 到 INFO 日志（之前未记录 prompt 详情，会导致请求信息不全）
        # 超过 500 字符仍截断；完整内容另会通过 log_llm_payload() 入 log
        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:openai] → {self.model} task={task_type} "
            f"max_tokens={kwargs.get('max_tokens', 4096)} "
            f"prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=kwargs.get("max_tokens", 4096),
                temperature=kwargs.get("temperature", 0.7),
            )
            duration_ms = (time.time() - t0) * 1000
            text = response.choices[0].message.content or ""
            # 响应预览：压缩空白后不超 300 字符，避免 log 一行被拆成多行
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:openai] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} response={response_preview_oneline!r}"
            )
            log_llm_payload(
                provider=self.provider_name,
                model=self.model,
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=prompt,
                response_text=text,
                duration_ms=duration_ms,
                success=True,
                extra={
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": (
                        response.usage.model_dump() if response.usage else None
                    ),
                },
            )
            return text
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:openai] ← {self.model} FAIL duration={duration_ms:.0f}ms: {e}",
                exc_info=True,
            )
            log_llm_payload(
                provider=self.provider_name,
                model=self.model,
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=prompt,
                response_text="",
                duration_ms=duration_ms,
                success=False,
                error=str(e),
            )
            raise

    def get_context_window(self) -> int:
        # GPT-4o context window
        return 128_000
