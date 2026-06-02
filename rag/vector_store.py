"""ChromaDB 向量存储封装"""
from pathlib import Path
from config import settings
import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, persist_path: str | None = None):
        self.persist_path = persist_path or settings.chroma_persist_dir
        Path(self.persist_path).mkdir(parents=True, exist_ok=True)
        self._client = None

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.persist_path,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def get_or_create_collection(self, name: str):
        """获取或创建 collection"""
        return self.client.get_or_create_collection(name=name)

    def delete_collection(self, name: str):
        """删除 collection"""
        try:
            self.client.delete_collection(name)
        except Exception:
            pass

    def list_collections(self) -> list[str]:
        """列出所有 collection"""
        return [c.name for c in self.client.list_collections()]
