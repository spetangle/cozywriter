"""Embedding 模型下载 API（含 SSE 进度推送）"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import time
from rag.model_manager import ModelManager, DEFAULT_MODEL


router = APIRouter(prefix="/api/models", tags=["模型管理"])


class ModelStatusResponse(BaseModel):
    model_name: str
    downloaded: bool
    cache_size_mb: float | None
    local_dir: str


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
        local_dir=str(manager.local_dir),
    )


@router.post("/download")
async def download_model_stream():
    """
    SSE 流式下载模型
    EventSource 客户端读取：data: {json}\\n\\n

    事件类型（data.stage 字段）：
      - "started": 开始
      - "migrating": 旧缓存迁移 (current=已迁移文件数, total=总文件数)
      - "downloading": 正在下载 (current=已下载字节, total=总字节)
      - "finished": 完成
      - "error": 错误
    """
    manager = ModelManager()

    async def event_generator():
        # 状态队列：model_manager 回调里 put，event_generator 异步 get
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        start_ts = time.time()

        def progress_cb(stage, current, total, message=""):
            # 从 huggingface_hub 的 tqdm 子线程回调；用线程安全方式投递
            try:
                payload = {
                    "stage": stage,
                    "current": current,
                    "total": total,
                    "message": message,
                    "elapsed_s": round(time.time() - start_ts, 1),
                }
                loop.call_soon_threadsafe(queue.put_nowait, payload)
            except Exception:
                pass

        # already exists → 立即推 finished
        if manager.is_model_downloaded():
            yield _sse({
                "stage": "finished",
                "current": 0,
                "total": 0,
                "message": "模型已存在",
                "elapsed_s": 0,
                "cache_size_mb": manager.get_cache_size_mb(),
            })
            return

        # 启动下载任务
        yield _sse({"stage": "started", "current": 0, "total": 0,
                    "message": f"开始下载 {manager.model_name}"})

        task = asyncio.create_task(
            asyncio.to_thread(manager.download_model, progress_cb)
        )

        # 推送进度
        try:
            while not task.done():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=0.5)
                    yield _sse(payload)
                except asyncio.TimeoutError:
                    # 心跳，避免 EventSource 被中间代理断开
                    yield _sse({"stage": "heartbeat", "current": 0, "total": 0,
                                "message": "", "elapsed_s": round(time.time() - start_ts, 1)})
            # task 完成，排空剩余
            while not queue.empty():
                try:
                    payload = queue.get_nowait()
                    yield _sse(payload)
                except asyncio.QueueEmpty:
                    break
            # 检查异常
            if task.exception():
                raise task.exception()  # type: ignore[misc]
        except Exception as e:
            yield _sse({
                "stage": "error",
                "current": 0,
                "total": 0,
                "message": str(e),
                "elapsed_s": round(time.time() - start_ts, 1),
            })
            return

        # 成功
        yield _sse({
            "stage": "finished",
            "current": 0,
            "total": 0,
            "message": "下载完成",
            "elapsed_s": round(time.time() - start_ts, 1),
            "cache_size_mb": manager.get_cache_size_mb(),
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(data: dict) -> str:
    """格式化 SSE 事件"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
