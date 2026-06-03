"""Embedding 模型管理器 - 下载、检测、缓存

模型统一存放在项目内 `./data/models/<model-name>/` 下（扁平结构），不依赖
`~/.cache/huggingface` 系统缓存。下载用 huggingface_hub 1.x 的 `local_dir`
参数（不再用 `cache_dir` 的嵌套 `models--org--name/snapshots/xxx` 结构）。
"""
import os
import gc
import shutil
from pathlib import Path
from huggingface_hub import snapshot_download
from config import settings


# 项目内模型根目录：./data/models/
MODEL_ROOT = Path(settings.data_dir) / "models"
DEFAULT_MODEL = settings.embedding_model


class ModelManager:
    """管理 sentence-transformers 模型的下载和加载"""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or DEFAULT_MODEL
        # 扁平目录：./data/models/<model-name>/
        # 例：./data/models/moka-ai/m3e-base/
        self.local_dir = MODEL_ROOT / self.model_name
        self._model = None

    def is_model_downloaded(self) -> bool:
        """检查模型是否已在项目内目录中
        判定标准：本地目录存在 + 至少有 config.json
        """
        if not self.local_dir.exists():
            return False
        # 关键文件存在性（任一即可）
        for fname in ["config.json", "modules.json", "tokenizer_config.json"]:
            if (self.local_dir / fname).exists():
                return True
        return False

    def download_model(self, progress_callback=None) -> str:
        """
        下载模型到项目内 ./data/models/<model-name>/

        Args:
            progress_callback: 可选进度回调
                fn(stage: str, current: int, total: int, message: str)
                - stage: "migrating" | "downloading" | "finished"
                - current / total: 字节数（migrating 时为文件数）
                - message: 人类可读描述

        Returns:
            模型本地路径（字符串）
        """
        self.local_dir.mkdir(parents=True, exist_ok=True)

        def _cb(stage, current, total, message=""):
            if progress_callback:
                try:
                    progress_callback(stage, current, total, message)
                except Exception:
                    pass  # 回调异常不阻断下载

        # 旧版嵌套缓存迁移：如果存在 ./data/models/models--xxx--yyy/snapshots/*/ 旧结构
        # 一次性复制到扁平目录（兼容升级）
        old_cache = MODEL_ROOT / ("models--" + self.model_name.replace("/", "--"))
        if old_cache.exists() and not self.is_model_downloaded():
            files = [p for p in old_cache.rglob("*") if p.is_file()]
            total = max(len(files), 1)
            for i, src in enumerate(files, 1):
                rel = src.relative_to(old_cache)
                # snapshots/<hash>/file -> <file>
                parts = rel.parts
                if len(parts) >= 2 and parts[0] == "snapshots":
                    rel = Path(*parts[2:]) if len(parts) > 2 else Path(parts[-1])
                dst = self.local_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    shutil.copy2(src, dst)
                _cb("migrating", i, total, f"迁移 {src.name}")
        _cb("downloading", 0, 0, f"开始下载 {self.model_name}")

        # 构造自定义 tqdm 类，把进度推到 progress_callback
        from tqdm.auto import tqdm

        outer_callback = progress_callback

        class _ProgressTqdm(tqdm):
            """tqdm 子类，实时回调当前/总数"""
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self._last_pct = -1
                self._outer = outer_callback

            def update(self, n=1):
                super().update(n)
                if self.total and self.n:
                    pct = int(self.n * 100 / self.total)
                    if pct != self._last_pct and pct % 2 == 0:
                        self._last_pct = pct
                        if self._outer:
                            try:
                                self._outer(
                                    "downloading",
                                    int(self.n),
                                    int(self.total),
                                    getattr(self, "desc", "") or "",
                                )
                            except Exception:
                                pass

            def close(self):
                if self._outer and self.total:
                    try:
                        self._outer(
                            "downloading",
                            int(self.total),
                            int(self.total),
                            "完成",
                        )
                    except Exception:
                        pass
                super().close()

        return snapshot_download(
            repo_id=self.model_name,
            local_dir=str(self.local_dir),
            local_dir_use_symlinks=False,
            resume_download=True,
            tqdm_class=_ProgressTqdm,
        )

    def load_model(self):
        """加载模型到内存"""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                str(self.local_dir),  # 直接传本地目录
            )
        return self._model

    def unload_model(self):
        """卸载模型，释放内存"""
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()

    def get_cache_size_mb(self) -> float | None:
        """获取模型大小（MB）"""
        if not self.local_dir.exists():
            return None
        total = sum(
            f.stat().st_size for f in self.local_dir.rglob("*") if f.is_file()
        )
        return round(total / 1024 / 1024, 1)

    def get_model_path(self) -> str:
        """返回模型本地路径（供其他模块使用）"""
        return str(self.local_dir)
