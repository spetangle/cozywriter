"""任务状态轮询 API"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from api.tasks import get_task, get_project_tasks, Task


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


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**task.to_dict())


@router.get("/project/{project_id}", response_model=list[TaskStatusResponse])
async def get_project_tasks_status(project_id: int):
    tasks = get_project_tasks(project_id)
    return [TaskStatusResponse(**t.to_dict()) for t in reversed(tasks)]
