"""Embedding 模型下载 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
from rag.model_manager import ModelManager, DEFAULT_MODEL


router = APIRouter(prefix="/api/models", tags=["模型管理"])


class ModelStatusResponse(BaseModel):
    model_name: str
    downloaded: bool
    cache_size_mb: float | None


class DownloadResponse(BaseModel):
    status: str  # already_exists / downloaded
    model_name: str
    cache_size_mb: float | None


@router.get("/status", response_model=ModelStatusResponse)
async def get_model_status():
    """查询 embedding 模型下载状态"""
    manager = ModelManager()
    downloaded = manager.is_model_downloaded()
    size = manager.get_cache_size_mb() if downloaded else None
    return ModelStatusResponse(
        model_name=manager.model_name,
        downloaded=downloaded,
        cache_size_mb=size,
    )


@router.post("/download", response_model=DownloadResponse)
async def download_model():
    """手动触发模型下载"""
    manager = ModelManager()
    if manager.is_model_downloaded():
        return DownloadResponse(
            status="already_exists",
            model_name=manager.model_name,
            cache_size_mb=manager.get_cache_size_mb(),
        )

    try:
        # 在线程池中执行下载（避免阻塞）
        await asyncio.to_thread(manager.download_model)
        return DownloadResponse(
            status="downloaded",
            model_name=manager.model_name,
            cache_size_mb=manager.get_cache_size_mb(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
