"""本地 Embedding 封装"""
import gc
from rag.model_manager import ModelManager, DEFAULT_MODEL


class LocalEmbedder:
    """
    本地 sentence-transformers embedding 封装
    延迟加载模型，按需加载/卸载
    """

    def __init__(self, model_name: str | None = None):
        self._manager = ModelManager(model_name)
        self._model = None

    @property
    def model_name(self) -> str:
        return self._manager.model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        将文本列表转为 embedding 向量

        Args:
            texts: 文本列表

        Returns:
            embedding 向量列表
        """
        if self._model is None:
            self._model = self._manager.load_model()
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_single(self, text: str) -> list[float]:
        """单文本 embedding"""
        return self.embed([text])[0]

    def unload(self):
        """卸载模型，释放内存"""
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()

    def is_ready(self) -> bool:
        """模型是否已加载"""
        return self._model is not None
