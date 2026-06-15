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
        if not provider:
            # db 未传入时，自动创建临时 session 读取数据库默认 provider
            _db = db
            if _db is None:
                try:
                    from storage.database import SessionLocal
                    _db = SessionLocal()
                except Exception:
                    _db = None
            if _db is not None:
                try:
                    from storage.models.system_setting import SystemSetting
                    provider = SystemSetting.get(_db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER)
                except Exception:
                    pass
                # 仅在自建 session 时关闭，调用方传入的 session 由调用方管理
                if db is None and _db is not None:
                    try:
                        _db.close()
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
