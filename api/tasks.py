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


def terminate_all_tasks() -> dict:
    """终止所有 pending/running 任务
    Returns:
        {"terminated": int, "skipped": int, "total": int}
    """
    with _tasks_lock:
        terminated = 0
        skipped = 0
        for t in _tasks.values():
            if t.status in ("pending", "running"):
                t.status = "cancelled"
                t.error = "用户终止"
                t.completed_at = time.time()
                terminated += 1
            else:
                skipped += 1
        return {
            "terminated": terminated,
            "skipped": skipped,
            "total": len(_tasks),
        }


def terminate_task(task_id: str) -> bool:
    """终止单个任务"""
    with _tasks_lock:
        t = _tasks.get(task_id)
        if not t:
            return False
        if t.status in ("pending", "running"):
            t.status = "cancelled"
            t.error = "用户终止"
            t.completed_at = time.time()
            return True
        return False


def run_task_async(task_id: str, fn: Callable, *args, **kwargs):
    """
    在线程池中运行任务，不阻塞 FastAPI 事件循环
    通过 BackgroundTasks 调用
    """
    task = get_task(task_id)
    if not task:
        return

    def _run():
        # 启动前检查是否已被标记取消（极小概率：submit 后立即终止）
        if task.status == "cancelled":
            return

        task.status = "running"
        task.started_at = time.time()
        task.progress = 10

        # 超时机制：用 threading.Timer 跨平台兼容（Windows 没有 Unix 的 alarm 信号）
        timeout_holder = {"hit": False}
        timer = None
        try:
            import threading
            def _on_timeout():
                timeout_holder["hit"] = True
                # 不能从 timer 线程里 raise（不会传到主线程），仅标记
            timer = threading.Timer(180.0, _on_timeout)
            timer.daemon = True
            timer.start()

            result = fn(*args, **kwargs)

            # LLM 调用结束后再次检查：用户是否在调用期间点了"终止"
            if task.status == "cancelled":
                logger.info(f"[Task {task_id}] user-cancelled during LLM call; discarding result")
                return

            # 检查超时
            if timeout_holder["hit"]:
                task.status = "failed"
                task.error = "任务超时（180秒）"
                task.completed_at = time.time()
                return

            task.progress = 100
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()

        except Exception as e:
            if task.status != "cancelled":
                task.status = "failed"
                task.error = str(e)
                task.completed_at = time.time()
        finally:
            if timer is not None:
                timer.cancel()

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


# ═══════════════════════════════════════════════════════════════
# 孤儿任务清理（启动时 / 手动）
# ═══════════════════════════════════════════════════════════════

def reap_orphan_tasks(reason: str = "服务重启") -> dict:
    """清理内存中的 pending/running 任务（标 cancelled）
    启动时调用，因为重启后内存是新进程的，这些是上个进程的"假活"任务。
    Returns: {"reaped": int, "kept": int}
    """
    with _tasks_lock:
        reaped = 0
        for t in _tasks.values():
            if t.status in ("pending", "running"):
                t.status = "cancelled"
                t.error = reason
                t.completed_at = time.time()
                reaped += 1
        return {"reaped": reaped, "kept": len(_tasks) - reaped}


def reap_orphan_workflow_runs(reason: str = "服务重启") -> dict:
    """清理 DB 中所有 pending/running 的 WorkflowRun（bootstrap 流程）
    启动时调用。返回: {"reaped": int, "kept": int, "ids": [...]}
    """
    from storage.models.workflow import WorkflowRun
    from storage.database import SessionLocal

    db = SessionLocal()
    try:
        stale = (
            db.query(WorkflowRun)
            .filter(WorkflowRun.status.in_(["pending", "running"]))
            .all()
        )
        ids = []
        for run in stale:
            run.status = "cancelled"
            run.updated_at = datetime.utcnow()
            # 把 stage_results 里的 running stage 标成 cancelled
            sr = dict(run.stage_results or {})
            for stage_id, info in sr.items():
                if isinstance(info, dict) and info.get("status") == "running":
                    sr[stage_id] = {
                        **info,
                        "status": "cancelled",
                        "error": reason,
                        "cancelled_at": time.time(),
                    }
            run.stage_results = sr
            ids.append(run.id)
        db.commit()
        return {"reaped": len(ids), "kept": 0, "ids": ids, "reason": reason}
    finally:
        db.close()


def reap_all_orphans() -> dict:
    """一站式清理：内存 + DB"""
    mem = reap_orphan_tasks("服务重启")
    db = reap_orphan_workflow_runs("服务重启")
    return {
        "memory_tasks": mem,
        "workflow_runs": db,
    }
