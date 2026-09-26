"""LLM Provider 工厂"""
from llm.base import LLMProvider
from llm.anthropic_provider import AnthropicProvider
from llm.openai_provider import OpenAIProvider
from llm.ollama_provider import OllamaProvider
from llm.minimax_provider import MiniMaxProvider
from llm.mimo_provider import MimoProvider
from llm.deepseek_provider import DeepSeekProvider
from llm.opencode_provider import OpencodeProvider
from config import settings


class LLMFactory:
    _providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "minimax": MiniMaxProvider,
        "mimo": MimoProvider,
        "deepseek": DeepSeekProvider,
        "opencode": OpencodeProvider,
    }

    @classmethod
    def create(cls, provider: str | None = None, db=None, **kwargs) -> LLMProvider:
        """创建 LLM Provider 实例

        provider 优先级：参数 > 数据库 Provider.is_default > SystemSetting > config.py
        配置优先级：数据库 Provider 记录 > .env > 默认值

        db: SQLAlchemy Session，用于从数据库读取配置
        """
        _db = db
        _should_close = False

        if _db is None:
            try:
                from storage.database import SessionLocal
                _db = SessionLocal()
                _should_close = True
            except Exception:
                _db = None

        try:
            if not provider and _db is not None:
                from storage.models.provider import Provider

                default_p = _db.query(Provider).filter(Provider.is_default == True).first()
                if default_p:
                    provider = default_p.id

            if not provider and _db is not None:
                from storage.models.system_setting import SystemSetting

                provider = SystemSetting.get(_db, SystemSetting.KEY_DEFAULT_LLM_PROVIDER)

            provider_key = (provider or settings.default_llm_provider or "").strip().lower()

            # opencode 仅在用户显式开启时可用
            if provider_key == "opencode" and not getattr(settings, "opencode_enabled", False):
                raise ValueError(
                    "opencode provider 未启用。请在 .env 中设置 OPENCODE_ENABLED=true 后重启。"
                )

            config_kwargs = {}
            if _db is not None and provider_key:
                from storage.models.provider import Provider

                p = _db.query(Provider).filter(Provider.id == provider_key).first()
                if p:
                    if p.api_key:
                        config_kwargs["api_key"] = p.api_key
                    if p.base_url:
                        config_kwargs["base_url"] = p.base_url
                    if p.model:
                        config_kwargs["model"] = p.model

            config_kwargs.update(kwargs)

            provider_cls = cls._providers.get(provider_key)
            if provider_cls is None:
                available = ", ".join(cls._providers.keys())
                raise ValueError(
                    f"Unknown provider: '{provider or settings.default_llm_provider}'. "
                    f"Available: {available}"
                )

            return provider_cls(**config_kwargs)
        finally:
            if _should_close and _db is not None:
                try:
                    _db.close()
                except Exception:
                    pass

    @classmethod
    def available_providers(cls) -> list[str]:
        """返回可用 provider 列表"""
        return list(cls._providers.keys())
