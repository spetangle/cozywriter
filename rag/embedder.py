"""Embedding 封装：本地 CPU 模型 / 在线 API 可切换"""
import gc

from rag.model_manager import ModelManager, DEFAULT_MODEL


class LocalEmbedder:
    """
    本地 sentence-transformers embedding 封装（强制 CPU）
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


def get_embedder(db=None, mode: str | None = None):
    """按系统设置返回 embedding 实现。

    - mode="local"（默认）：本地 CPU 模型（需 sentence-transformers + 已下载模型）
    - mode="online"：在线 OpenAI 兼容 embedding API

    在线模式未配置完整（缺 key/model）时回退本地，避免主流程报错。
    """
    from storage.models.system_setting import SystemSetting

    should_close = False
    if db is None:
        try:
            from storage.database import SessionLocal
            db = SessionLocal()
            should_close = True
        except Exception:
            db = None

    try:
        if mode is None and db is not None:
            mode = SystemSetting.get(db, SystemSetting.KEY_RAG_EMBEDDING_MODE, "local")
        mode = (mode or "local").strip().lower()

        if mode == "online" and db is not None:
            base_url = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_BASE_URL, "")
            api_key = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_API_KEY, "")
            model = SystemSetting.get(db, SystemSetting.KEY_RAG_ONLINE_MODEL, "")
            if api_key and model:
                from rag.online_embedder import OnlineEmbedder
                return OnlineEmbedder(base_url=base_url, api_key=api_key, model=model)
            import logging
            logging.getLogger(__name__).warning(
                "[RAG] 在线 embedding 未配置完整（缺 API Key 或模型名），回退本地模型"
            )
        return LocalEmbedder()
    finally:
        if should_close and db is not None:
            try:
                db.close()
            except Exception:
                pass
