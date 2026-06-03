"""LLM Provider 抽象基类"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """所有 LLM Provider 必须实现的接口"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称 (anthropic / openai / ollama)"""
        ...

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        """同步生成文本"""
        ...

    @abstractmethod
    def get_context_window(self) -> int:
        """上下文窗口大小（tokens）"""
        ...
