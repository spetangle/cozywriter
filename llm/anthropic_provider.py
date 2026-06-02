"""Anthropic (Claude) Provider"""
from llm.base import LLMProvider
from config import settings
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

        messages = [{"role": "user", "content": prompt}]
        response = client.messages.create(
            model=self.model,
            system=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.content[0].text

    def get_context_window(self) -> int:
        # Claude Sonnet 4 context window
        return 200_000
