"""Anthropic (Claude) Provider"""
import time
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
import anthropic


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        max_tokens = kwargs.get("max_tokens", 4096)
        # task_type 透传：调用方可在 kwargs 里指定（如 "stage_1_base"），方便 log 分类
        task_type = kwargs.get("task_type", "generate")
        messages = [{"role": "user", "content": prompt}]

        # 记录完整 prompt 到 INFO 日志（之前只截断 80 字会导致请求信息不全）
        # 超过 500 字符仍然截断，避免刷屏；完整内容另外会通过 log_llm_payload() 入 log
        prompt_preview = prompt if len(prompt) <= 500 else prompt[:500] + "..."
        logger.info(
            f"[LLM:anthropic] → {self.model} max_tokens={max_tokens} "
            f"task={task_type} prompt_chars={len(prompt)} prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            response = client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=messages,
                max_tokens=max_tokens,
            )
            duration_ms = (time.time() - t0) * 1000
            # 提取文本（多 block 拼接）
            text = "".join(
                block.text for block in response.content
                if getattr(block, "type", None) == "text"
            )
            # 响应预览：压缩空白后不超 300 字符，避免 log 一行被拆成多行
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:anthropic] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} response={response_preview_oneline!r}"
            )
            # 完整 payload 入 log 文件（DEBUG 级，不刷屏 console）
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
                    "stop_reason": getattr(response, "stop_reason", None),
                    "input_tokens": getattr(getattr(response, "usage", None), "input_tokens", None),
                    "output_tokens": getattr(getattr(response, "usage", None), "output_tokens", None),
                    "content_blocks": [
                        getattr(b, "type", "?") for b in (response.content or [])
                    ],
                },
            )
            return text
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(f"[LLM:anthropic] ← {self.model} FAIL duration={duration_ms:.0f}ms error={e}", exc_info=True)
            # 失败也记 payload（response 是空字符串）
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
        # Claude Sonnet 4 context window
        return 200_000
