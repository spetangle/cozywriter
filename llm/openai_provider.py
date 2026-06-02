"""OpenAI (GPT) Provider"""
from llm.base import LLMProvider
from config import settings
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content

    def get_context_window(self) -> int:
        # GPT-4o context window
        return 128_000
