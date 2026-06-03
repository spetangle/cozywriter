"""LLM Provider 工厂"""
from llm.base import LLMProvider
from llm.anthropic_provider import AnthropicProvider
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider
from llm.minimax_provider import MiniMaxProvider
from config import settings


class LLMFactory:
    _providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "MiniMax": MiniMaxProvider,
    }

    @classmethod
    def create(cls, provider: str | None = None, **kwargs) -> LLMProvider:
        """创建 LLM Provider 实例"""
        provider = provider or settings.default_llm_provider
        provider_cls = cls._providers.get(provider)
        if provider_cls is None:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unknown provider: {provider}. Available: {available}")
        return provider_cls(**kwargs)

    @classmethod
    def available_providers(cls) -> list[str]:
        """返回可用 provider 列表"""
        return list(cls._providers.keys())
