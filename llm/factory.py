"""LLM Provider 工厂"""
from llm.base import LLMProvider
from llm.anthropic_provider import AnthropicProvider
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider
from llm.minimax_provider import MiniMaxProvider
from llm.mimo_provider import MimoProvider
from config import settings


class LLMFactory:
    # key 全部小写（创建时强制 lowercase 查找）
    _providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "minimax": MiniMaxProvider,
        "mimo": MimoProvider,
    }

    @classmethod
    def create(cls, provider: str | None = None, db=None, **kwargs) -> LLMProvider:
        """创建 LLM Provider 实例

        provider 优先级：参数 > 数据库 SystemSetting > config.py
        db: SQLAlchemy Session，用于从数据库读取默认 provider
        """
        if not provider and db is not None:
            try:
                from storage.models.system_setting import SystemSetting
                provider = SystemSetting.get(db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER)
            except Exception:
                pass

        provider_key = (provider or settings.default_llm_provider or "").strip().lower()
        provider_cls = cls._providers.get(provider_key)
        if provider_cls is None:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Unknown provider: '{provider or settings.default_llm_provider}'. "
                f"Available: {available}"
            )
        return provider_cls(**kwargs)

    @classmethod
    def available_providers(cls) -> list[str]:
        """返回可用 provider 列表"""
        return list(cls._providers.keys())
