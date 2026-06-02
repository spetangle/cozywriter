"""LLM Provider 抽象基类"""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """LLM provider 抽象基类"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        """
        生成文本

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            **kwargs: provider 特定参数

        Returns:
            生成的文本
        """
        ...

    @abstractmethod
    def get_context_window(self) -> int:
        """返回上下文窗口大小（token 数）"""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 名称"""
        ...
