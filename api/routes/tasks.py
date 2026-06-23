"""任务状态轮询 API"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from api.tasks import get_task, get_project_tasks, Task, terminate_all_tasks, terminate_task


router = APIRouter(prefix="/api/tasks", tags=["任务管理"])


class TaskStatusResponse(BaseModel):
    id: str
    task_type: str
    description: str
    status: str
    progress: int
    result: dict | None
    error: str
    duration_s: float


# 注意：FastAPI 路由按声明顺序匹配。具体路径（/all, /project/..., /terminate-all）
# 必须放在 /{task_id} 之前，否则会被当成 task_id 解析。

@router.get("/all", response_model=list[TaskStatusResponse])
async def get_all_tasks():
    """获取所有任务（按 created_at 倒序）"""
    from api.tasks import _tasks, _tasks_lock
    with _tasks_lock:
        tasks = list(_tasks.values())
    tasks.sort(key=lambda t: t.created_at, reverse=True)
    return [TaskStatusResponse(**t.to_dict()) for t in tasks]


@router.get("/project/{project_id}", response_model=list[TaskStatusResponse])
async def get_project_tasks_status(project_id: str):
    tasks = get_project_tasks(project_id)
    return [TaskStatusResponse(**t.to_dict()) for t in reversed(tasks)]


@router.post("/terminate-all")
async def terminate_all():
    """终止所有 pending/running 任务"""
    return terminate_all_tasks()


@router.post("/cleanup")
async def cleanup_orphans():
    """清理孤儿任务（pending/running 但实际已死）

    用场景：
    - 浏览器看到 banner 一直显示"AI 补全进行中"但实际没在跑
    - 怀疑有 stale 状态
    - 正常服务重启时也会自动调用（不需要手动）
    """
    from api.tasks import reap_all_orphans
    return reap_all_orphans()


# 单 task 路径（放在最后，确保具体路径优先匹配）
@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**task.to_dict())


@router.post("/{task_id}/terminate")
async def terminate_one(task_id: str):
    """终止单个任务"""
    ok = terminate_task(task_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found or already finished")
    return {"status": "cancelled", "task_id": task_id}
