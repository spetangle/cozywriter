"""
异步任务管理 - LLM 调用不阻塞主程序

任务状态：
  pending → running → completed / failed

前端通过轮询 /api/tasks/{task_id} 获取结果
"""

import uuid
import time
import asyncio
import threading
from datetime import datetime
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

# 全局线程池（用于运行 LLM 调用）
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="llm_task")


@dataclass
class Task:
    id: str
    task_type: str  # "generate" / "review" / "consistency"
    description: str
    status: str = "pending"  # pending / running / completed / failed
    progress: int = 0  # 0-100
    result: Any = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration_s(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_type": self.task_type,
            "description": self.description,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "duration_s": round(self.duration_s, 1),
            "created_at": self.created_at,
        }


# 任务存储（内存）
_tasks: dict[str, Task] = {}
_tasks_lock = threading.Lock()


def create_task(task_type: str, description: str) -> Task:
    """创建新任务"""
    task_id = str(uuid.uuid4())[:8]
    task = Task(id=task_id, task_type=task_type, description=description)
    with _tasks_lock:
        _tasks[task_id] = task
    return task


def get_task(task_id: str) -> Task | None:
    with _tasks_lock:
        return _tasks.get(task_id)


def get_project_tasks(project_id: int) -> list[Task]:
    """获取项目下所有任务"""
    with _tasks_lock:
        return [t for t in _tasks.values() if str(project_id) in t.description]


def run_task_async(task_id: str, fn: Callable, *args, **kwargs):
    """
    在线程池中运行任务，不阻塞 FastAPI 事件循环
    通过 BackgroundTasks 调用
    """
    task = get_task(task_id)
    if not task:
        return

    def _run():
        task.status = "running"
        task.started_at = time.time()
        task.progress = 10

        try:
            # 设置超时
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Task {task_id} timed out")

            # 默认超时 180 秒
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(180)

            result = fn(*args, **kwargs)

            signal.alarm(0)
            task.progress = 100
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()

        except TimeoutError as e:
            task.status = "failed"
            task.error = f"任务超时（180秒）: {str(e)}"
            task.completed_at = time.time()

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()

    _executor.submit(_run)


# ─── 快捷调用接口 ───

def submit_llm_task(
    task_type: str,
    llm_call_fn: Callable,
    project_id: int,
    description: str,
    *args,
    **kwargs,
) -> Task:
    """
    提交一个 LLM 异步任务

    Args:
        task_type: generate / review / consistency
        llm_call_fn: 实际执行 LLM 调用的同步函数
        project_id: 关联项目 ID
        description: 任务描述
    """
    task = create_task(task_type, f"[P{project_id}] {description}")
    run_task_async(task.id, llm_call_fn, *args, **kwargs)
    return task
