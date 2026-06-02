"""Ollama 本地模型 Provider"""
from llm.base import LLMProvider
from config import settings
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
            self._client = httpx.Client(base_url=self.base_url, timeout=120)
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()

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

        response = client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json().get("response", "")

    def get_context_window(self) -> int:
        # Ollama 默认 context window，取决于模型配置
        return 8192
