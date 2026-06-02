"""Embedding 模型管理器 - 下载、检测、缓存"""
import os
import gc
from pathlib import Path
from huggingface_hub import snapshot_check, snapshot_download
from config import settings


MODEL_CACHE_DIR = Path(settings.data_dir) / "models"
DEFAULT_MODEL = settings.embedding_model


class ModelManager:
    """管理 sentence-transformers 模型的下载和加载"""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or DEFAULT_MODEL
        self.cache_dir = MODEL_CACHE_DIR
        self._model = None

    def is_model_downloaded(self) -> bool:
        """检查模型是否已在本地缓存"""
        try:
            # 先检查环境变量中的镜像
            if os.environ.get("HF_ENDPOINT"):
                os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
            return snapshot_check(
                self.model_name,
                cache_dir=str(self.cache_dir),
            )
        except Exception:
            return False

    def download_model(self) -> str:
        """
        下载模型到本地缓存

        Returns:
            模型本地路径
        """
        return snapshot_download(
            self.model_name,
            cache_dir=str(self.cache_dir),
            resume_download=True,
            local_files_only=False,
        )

    def load_model(self):
        """加载模型到内存"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                cache_folder=str(self.cache_dir),
            )
        return self._model

    def unload_model(self):
        """卸载模型，释放内存"""
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()

    def get_cache_size_mb(self) -> float | None:
        """获取模型缓存大小（MB）"""
        if not self.is_model_downloaded():
            return None
        model_path = self.cache_dir / self.model_name.replace("/", "--")
        if not model_path.exists():
            return None
        total = sum(f.stat().st_size for f in model_path.rglob("*") if f.is_file())
        return round(total / 1024 / 1024, 1)
