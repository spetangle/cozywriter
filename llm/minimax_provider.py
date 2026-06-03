"""MiniMax Provider (MiniMax 大模型)

官方文档：https://platform.minimaxi.com/docs/guides/models-intro

API 规范（Anthropic Messages 兼容）：
- Base URL：https://api.minimaxi.com  (无 /v1 后缀)
- 端点：POST {base_url}/anthropic/v1/messages
- 认证：Authorization: Bearer <API_KEY>  (同时发 x-api-key 双兼容)
- 模型：
    * MiniMax-M3         (多模态：文本+图片+视频，1M 上下文，Coding/Agentic SOTA)
    * MiniMax-M2.7       (文本+工具)
    * MiniMax-M2.5
    * MiniMax-M2.1
    * MiniMax-M2
- 默认温度：1.0
- max_tokens 推荐：M3=131072 (128K)，M2.x=65536 (64K)
- 请求体格式：Anthropic Messages API 风格（不是 OpenAI chat.completions）
- 响应：content 是块数组 [{type:text, text:"..."}]，需要提取 type=text 的 text 拼接

实现策略：直接用 httpx 调，避免 anthropic SDK 依赖膨胀。
"""
from llm.base import LLMProvider
from config import settings
import httpx


class MiniMaxProvider(LLMProvider):
    # 官方 base
    DEFAULT_BASE_URL = "https://api.minimaxi.com"
    # 缺省模型：M2.7 文本主力（兼容所有用户账号；M3 可能需单独开通多模态权限）
    DEFAULT_MODEL = "MiniMax-M2.7"
    # 上下文窗口：M3=1M, M2.x=128K，统一按 128K 报
    CONTEXT_WINDOW = 128_000

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or settings.minimax_api_key
        self.model = model or getattr(settings, "minimax_model", None) or self.DEFAULT_MODEL
        self.base_url = (
            base_url
            or getattr(settings, "minimax_base_url", None)
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "MiniMax"

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            # Authorization + x-api-key 双发（官方：同时存在时优先 Authorization）
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(180.0, connect=30.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
            )
        return self._client

    def _recommended_max_tokens(self) -> int:
        """根据模型返回推荐的 max_tokens"""
        if "M3" in self.model:
            return 131072
        return 65536  # M2.x

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        **kwargs,
    ) -> str:
        client = self._get_client()

        # Anthropic Messages 格式
        messages = [{"role": "user", "content": prompt}]

        # system 可以是字符串或块数组；这里走最简字符串
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens") or self._recommended_max_tokens(),
            "temperature": kwargs.get("temperature", 1.0),
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = client.post("/anthropic/v1/messages", json=payload)
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"MiniMax 网络请求失败（{self.base_url}）: {e}"
            ) from e

        # 友好错误信息
        if response.status_code == 401:
            raise RuntimeError(
                "MiniMax 鉴权失败 (401)。请检查 .env 中 MINIMAX_API_KEY 是否正确。\n"
                "获取 API Key: https://platform.minimaxi.com/user-center/basic-information/interface-key"
            )
        if response.status_code == 403:
            raise RuntimeError(
                f"MiniMax 403: 无权访问模型 '{self.model}'。"
                f"该模型可能需要单独开通权限。可选: MiniMax-M2.7 / M2.5 / M2.1 / M2"
            )
        if response.status_code == 404:
            raise RuntimeError(
                f"MiniMax 404: 模型 '{self.model}' 不存在或 base_url '{self.base_url}' 错误。"
            )
        if response.status_code == 429:
            raise RuntimeError("MiniMax 触发限流 (429)，请稍后重试。")
        response.raise_for_status()

        data = response.json()

        # Anthropic Messages 响应：content 是块数组
        try:
            content_blocks = data["content"]
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"MiniMax 返回格式异常（无 content 字段）: {data}") from e

        # 提取所有 type=text 的块，按顺序拼接
        # 跳过 type=thinking / type=tool_use 等非文本块
        parts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))

        if not parts:
            # 模型只返回了 thinking 而无 text（开了 thinking 且 max_tokens 不够）
            raise RuntimeError(
                f"MiniMax 返回无 text 块（可能开了 thinking 且 max_tokens 不足）。"
                f"响应: {data}"
            )

        return "".join(parts)

    def get_context_window(self) -> int:
        return self.CONTEXT_WINDOW
