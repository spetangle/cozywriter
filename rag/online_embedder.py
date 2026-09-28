"""在线 Embedding 封装（OpenAI 兼容 /embeddings 接口）

用于在没有本地 CPU embedding 模型、或希望用在线服务时提供 RAG 向量。
兼容 OpenAI / DeepSeek / OpenCode 等提供 OpenAI 兼容 embeddings 的服务。
"""
from openai import OpenAI

from logger import logger


class OnlineEmbedder:
    """在线 embedding API（OpenAI 兼容）"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
    ):
        if not api_key:
            raise ValueError("在线 embedding 需要 API Key")
        if not model:
            raise ValueError("在线 embedding 需要模型名")

        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=self.base_url or None,
            timeout=timeout,
            max_retries=2,
        )

    @property
    def model_name(self) -> str:
        return self.model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self.model, input=texts)
        # 按 index 排序，保证与输入顺序一致
        data = sorted(resp.data, key=lambda d: getattr(d, "index", 0))
        return [list(d.embedding) for d in data]

    def embed_single(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def unload(self):
        """在线模式无需卸载；保留接口兼容。"""
        return None

    def is_ready(self) -> bool:
        return bool(self.api_key and self.model)

    def test(self) -> dict:
        """测试连通性，返回维度等信息。"""
        vec = self.embed_single("CozyWriter RAG 连通性测试")
        return {"ok": True, "dimension": len(vec), "model": self.model}
