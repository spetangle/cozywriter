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

from logger import logger

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
    project_id: int = 0  # 关联项目 ID（方便清理时反查）
    run_id: Optional[int] = None  # 关联的 WorkflowRun.id（用于取消时同步 DB）

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
            "project_id": self.project_id,
            "run_id": self.run_id,
        }


# 任务存储（内存）
_tasks: dict[str, Task] = {}
_tasks_lock = threading.Lock()


def create_task(task_type: str, description: str, project_id: int = 0, run_id: int | None = None) -> Task:
    """创建新任务"""
    task_id = str(uuid.uuid4())[:8]
    task = Task(
        id=task_id,
        task_type=task_type,
        description=description,
        project_id=project_id,
        run_id=run_id,
    )
    with _tasks_lock:
        _tasks[task_id] = task
    logger.info(f"[Task {task_id}] 创建 task_type={task_type} project={project_id} run={run_id} desc={description!r}")
    return task


def get_task(task_id: str) -> Task | None:
    with _tasks_lock:
        return _tasks.get(task_id)


def get_project_tasks(project_id: int) -> list[Task]:
    """获取项目下所有任务"""
    with _tasks_lock:
        return [t for t in _tasks.values() if t.project_id == project_id]


def _sync_db_run_cancelled(run_id: int, reason: str) -> bool:
    """把 DB WorkflowRun 标记为 cancelled（让 banner 和 task list 状态一致）"""
    if not run_id:
        return False
    try:
        from storage.database import SessionLocal
        from storage.models.workflow import WorkflowRun
        db = SessionLocal()
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if not run:
                return False
            if run.status in ("cancelled", "committed"):
                return False
            run.status = "cancelled"
            run.updated_at = datetime.utcnow()
            # 把 stage_results 里仍在 running 的 stage 标 cancelled
            sr = dict(run.stage_results or {})
            for sid, info in sr.items():
                if isinstance(info, dict) and info.get("status") == "running":
                    # 关键：同时设 completed_at，让前端的"已耗时"停止累加
                    sr[sid] = {
                        **info,
                        "status": "cancelled",
                        "error": reason,
                        "completed_at": time.time(),
                    }
            run.stage_results = sr
            db.commit()
            logger.info(f"[Task→DB] run {run_id} 标记为 cancelled (reason={reason!r})")
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Task→DB] sync cancelled failed for run {run_id}: {e}")
        return False


def _refresh_inmem_task_from_run(run_id: int) -> int:
    """
    rerun-all 完成后，把 in-memory 中 run_id 匹配的任务刷新到 DB 最新状态。
    让前端 /api/tasks/all 拉到的状态立即反映 rerun 结果。

    Returns:
        更新的任务数
    """
    if not run_id:
        return 0
    try:
        from storage.database import SessionLocal
        from storage.models.workflow import WorkflowRun
        db = SessionLocal()
        try:
            run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if not run:
                return 0
            new_status = run.status  # pending / running / completed / failed / partial / cancelled / committed
            # 映射：DB committed → 内存 completed
            mem_status = "completed" if new_status == "committed" else new_status
            updated = 0
            with _tasks_lock:
                for t in _tasks.values():
                    if t.run_id == run_id and t.status in ("failed", "cancelled", "running", "pending"):
                        t.status = mem_status
                        t.completed_at = time.time()
                        if mem_status in ("completed", "failed", "cancelled"):
                            # 把 run 的最新 stage_results 同步到 task.result
                            t.result = {
                                "run_status": new_status,
                                "stage_results": run.stage_results or {},
                                "current_stage_index": run.current_stage_index,
                            }
                        # 如果是 failed，error 留之前的；否则清掉
                        if mem_status != "failed":
                            t.error = ""
                        logger.info(
                            f"[Task↔DB] task {t.id} (run={run_id}) status → {mem_status}"
                        )
                        updated += 1
            return updated
        finally:
            db.close()
    except Exception as e:
        logger.error(f"[Task↔DB] refresh failed for run {run_id}: {e}")
        return 0


def terminate_all_tasks() -> dict:
    """终止所有 pending/running 任务
    Returns:
        {"terminated": int, "skipped": int, "total": int}
    """
    with _tasks_lock:
        to_terminate = [
            t for t in _tasks.values()
            if t.status in ("pending", "running")
        ]
        for t in to_terminate:
            t.status = "cancelled"
            t.error = "用户终止"
            t.completed_at = time.time()
        total = len(_tasks)
        terminated = len(to_terminate)
        skipped = total - terminated

    # DB 同步（在锁外做）
    for t in to_terminate:
        if t.run_id:
            _sync_db_run_cancelled(t.run_id, "用户终止")

    logger.info(f"[Task] terminate-all: terminated={terminated} skipped={skipped} total={total}")
    return {
        "terminated": terminated,
        "skipped": skipped,
        "total": total,
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
            run_id = t.run_id
        else:
            return False

    # DB 同步（在锁外做，避免锁内做 IO）
    if run_id:
        _sync_db_run_cancelled(run_id, "用户终止")
    logger.info(f"[Task {task_id}] terminated by user (run_id={run_id})")
    return True


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
            logger.info(f"[Task {task_id}] 已标记取消，跳过启动")
            return

        task.status = "running"
        task.started_at = time.time()
        task.progress = 10
        logger.info(f"[Task {task_id}] START ({fn.__name__}) project={task.project_id} run={task.run_id}")

        # 超时机制：用 threading.Timer 跨平台兼容（Windows 没有 Unix 的 alarm 信号）
        timeout_holder = {"hit": False}
        timer = None
        try:
            import threading
            def _on_timeout():
                timeout_holder["hit"] = True
                # 不能从 timer 线程里 raise（不会传到主线程），仅标记
            timer = threading.Timer(600.0, _on_timeout)
            timer.daemon = True
            timer.start()

            result = fn(task_id, *args, **kwargs)

            # LLM 调用结束后再次检查：用户是否在调用期间点了"终止"
            if task.status == "cancelled":
                logger.info(f"[Task {task_id}] user-cancelled during LLM call; discarding result")
                return

            # 检查超时
            if timeout_holder["hit"]:
                task.status = "failed"
                task.error = "任务超时（600秒）"
                task.completed_at = time.time()
                logger.warning(f"[Task {task_id}] timeout (180s)")
                return

            task.progress = 100
            task.status = "completed"
            task.result = result
            task.completed_at = time.time()
            logger.info(
                f"[Task {task_id}] DONE duration={task.duration_s:.1f}s "
                f"project={task.project_id} run={task.run_id}"
            )

        except Exception as e:
            if task.status != "cancelled":
                task.status = "failed"
                task.error = str(e)
                task.completed_at = time.time()
                logger.error(
                    f"[Task {task_id}] FAILED project={task.project_id} run={task.run_id}: {e}",
                    exc_info=True,
                )
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
        **kwargs:
            run_id: int | None   关联的 WorkflowRun.id（取消时同步 DB）
            其他 kwargs 透传给 llm_call_fn
    """
    # 读取 run_id（不 pop），让它继续在 kwargs 里传给 fn
    run_id = kwargs.get("run_id")
    task = create_task(
        task_type,
        f"[P{project_id}] {description}",
        project_id=project_id,
        run_id=run_id,
    )
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
    同步：把对应 run_id 的 in-memory Task 也标 cancelled（保持两侧一致）
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
        in_mem_cancelled = []
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
                        "completed_at": time.time(),  # 同时设 completed_at 让前端停止计时
                    }
            run.stage_results = sr
            ids.append(run.id)

            # 反向同步：把 in-memory 中 run_id 匹配的任务也标 cancelled
            with _tasks_lock:
                for t in list(_tasks.values()):
                    if t.run_id == run.id and t.status in ("pending", "running"):
                        t.status = "cancelled"
                        t.error = f"{reason} (run={run.id})"
                        t.completed_at = time.time()
                        in_mem_cancelled.append(t.id)

        db.commit()
        logger.info(
            f"[Orphan reap] DB runs reaped={len(ids)} ids={ids}; "
            f"in-memory tasks cancelled={in_mem_cancelled}"
        )
        return {
            "reaped": len(ids),
            "kept": 0,
            "ids": ids,
            "reason": reason,
            "in_mem_cancelled": in_mem_cancelled,
        }
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
