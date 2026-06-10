"""Ollama 本地模型 Provider"""
import time
from llm.base import LLMProvider
from config import settings
from logger import logger, log_llm_payload
import httpx


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str | None = None,
        model: str = "qwen2.5",
    ):
        self.base_url = base_url or settings.ollama_base_url
        self.model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "ollama"

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=600)
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()
        task_type = kwargs.get("task_type", "generate")

        # Ollama 的 /api/generate 协议把 system+user 拼成单个 prompt
        # （不像 Anthropic 有独立 system 字段），所以 system_prompt 拼到前面，
        # 入 log 时仍然按"system"和"user"两个字段记录，方便统一查看
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "num_predict": kwargs.get("max_tokens", 4096),
            },
        }

        # 记录完整 prompt 到 INFO 日志（之前只有 prompt_chars，无具体内容）
        # 超过 500 字符仍截断；完整内容另会通过 log_llm_payload() 入 log
        prompt_preview = full_prompt if len(full_prompt) <= 500 else full_prompt[:500] + "..."
        logger.info(
            f"[LLM:ollama] → {self.model} task={task_type} "
            f"base={self.base_url} prompt_chars={len(full_prompt)} "
            f"prompt={prompt_preview!r}"
        )
        t0 = time.time()
        try:
            response = client.post("/api/generate", json=payload)
            duration_ms = (time.time() - t0) * 1000
            response.raise_for_status()
            text = response.json().get("response", "")
            # 响应预览：压缩空白后不超 300 字符，避免 log 一行被拆成多行
            response_preview = text if len(text) <= 300 else text[:300] + "..."
            response_preview_oneline = " ".join(response_preview.split())
            logger.info(
                f"[LLM:ollama] ← {self.model} ok duration={duration_ms:.0f}ms "
                f"chars={len(text)} response={response_preview_oneline!r}"
            )
            # 完整 payload 入 log 文件
            log_llm_payload(
                provider=self.provider_name,
                model=self.model,
                task_type=task_type,
                system_prompt=system_prompt,
                user_prompt=prompt,
                response_text=text,
                duration_ms=duration_ms,
                success=True,
                extra={"base_url": self.base_url},
            )
            return text
        except Exception as e:
            duration_ms = (time.time() - t0) * 1000
            logger.error(
                f"[LLM:ollama] ← {self.model} FAIL duration={duration_ms:.0f}ms: {e}",
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
                extra={"base_url": self.base_url},
            )
            raise

    def get_context_window(self) -> int:
        # Ollama 默认 context window，取决于模型配置
        return 8192
