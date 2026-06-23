"""工作流管理 API - 重跑 / 提交 / 状态查询"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.workflow import WorkflowRun
from logger import logger
import threading as _threading


router = APIRouter(prefix="/api/workflow", tags=["工作流"])


# ─── In-process 锁：防止同一 run 并发重跑 ───
# 背景：rerun-all 异步提交到线程池，10s 内连点 2 次会同时跑 2 个 task，
#      都会改 run.stage_results → 竞态 → 数据混乱
# 范围：进程内（单实例足够；多实例需要走 DB 锁，但当前是单机）
# 粒度：per-run_id
# 自动释放：task 跑完（无论成功失败）→ 释放
_inflight_runs: set[int] = set()
_inflight_lock = _threading.Lock()


def _acquire_run_lock(run_id: int) -> bool:
    """尝试加锁。返回 True=拿到锁 / False=已被别的 task 占用"""
    with _inflight_lock:
        if run_id in _inflight_runs:
            return False
        _inflight_runs.add(run_id)
        return True


def _release_run_lock(run_id: int) -> None:
    with _inflight_lock:
        _inflight_runs.discard(run_id)


# ─── Schemas ───

class RerunRequest(BaseModel):
    stage_id: str


class CommitResponse(BaseModel):
    status: str  # committed / failed / already_committed
    summary: dict = {}
    error: str | None = None


class WorkflowStatusResponse(BaseModel):
    run_id: int
    project_id: str
    name: str
    status: str
    current_stage_index: int
    stages: list[dict] = []
    stage_results: dict = {}
    created_at: object
    updated_at: object


# ─── Helpers ───

def merge_stage_results(stages: list[dict], stage_results: dict) -> list[dict]:
    """
    把 stage_results 里的实时状态合并到每个 stage 上。

    原因：run.stages 是 plan_bootstrap_stages 生成的静态定义（status 始终 "pending"），
    真正的 per-stage 状态在 run.stage_results[id].status（"running" / "ok" / "failed" / "skipped" / "user_filled"）。
    前端读 stage.status，所以这里把 stage_results 合并进来。
    同时挂上每个 stage 的 started_at / completed_at / elapsed_s，方便前端显示耗时。
    """
    out = []
    import time as _time
    for stage in (stages or []):
        sid = stage.get("id", "")
        sr = (stage_results or {}).get(sid) or {}
        merged = dict(stage)
        status = sr.get("status", stage.get("status", "pending"))
        merged["status"] = status
        # 时间戳（让前端能算每个 stage 的耗时）
        started_at = sr.get("started_at")
        completed_at = sr.get("completed_at")
        # 防御 started_at 看起来无效（sentinel 值/0/epoch 早期）：
        # 任何小于 2001-09-09 (1_000_000_000) 的时间戳视为无效，丢弃
        if started_at is not None and started_at < 1_000_000_000:
            started_at = None
        if completed_at is not None and completed_at < 1_000_000_000:
            completed_at = None
        # 防御：终态但缺 completed_at → 补成 now（保留实际运行时长，停止累加）
        if status in ("ok", "user_filled", "skipped", "failed", "cancelled") and started_at and not completed_at:
            completed_at = _time.time()
        # 防御：running 但缺 started_at（极端 race / 残留脏数据）
        # → 不挂 started_at，前端会 return 空；再单独挂 elapsed_s=None 让前端知道"无法计算"
        if started_at:
            merged["started_at"] = started_at
        if completed_at:
            merged["completed_at"] = completed_at
        if started_at and completed_at:
            merged["elapsed_s"] = round(completed_at - started_at, 1)
        elif started_at and status == "running":
            # 还在跑：用当前时间算"已耗时"
            merged["elapsed_s"] = round(_time.time() - started_at, 1)
        # running 缺 started_at：明确不挂 elapsed_s，让前端兜底 return ''
        if sr.get("error"):
            merged["error"] = sr["error"]
        out.append(merged)
    return out


# ─── Routes ───

@router.get("/in-flight")
async def get_in_flight_run(db: Session = Depends(get_db)):
    """获取当前进行中的 workflow run（供页面刷新/重连时恢复 wizard）

    返回：
      - {"run": null}: 没有进行中的 run
      - {"run": {...}}: 最新一个 status in (pending/running) 的 run
    """
    from storage.models.workflow import WorkflowRun

    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.status.in_(["pending", "running"]))
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if not run:
        return {"run": None}
    return {
        "run": {
            "run_id": run.id,
            "project_id": run.project_id,
            "name": run.name,
            "status": run.status,
            "stages": merge_stage_results(run.stages or [], run.stage_results or {}),
            "stage_results": run.stage_results or {},
        }
    }


@router.get("/run/{run_id}", response_model=WorkflowStatusResponse)
async def get_run(run_id: int, db: Session = Depends(get_db)):
    """获取 workflow run 完整状态"""
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return WorkflowStatusResponse(
        run_id=run.id,
        project_id=run.project_id,
        name=run.name,
        status=run.status,
        current_stage_index=run.current_stage_index,
        stages=merge_stage_results(run.stages or [], run.stage_results or {}),
        stage_results=run.stage_results or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/project/{project_id}/latest")
async def get_latest_run(project_id: str, db: Session = Depends(get_db)):
    """获取项目最近的 workflow run（通常是 bootstrap）"""
    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No run found for this project")
    return {
        "run_id": run.id,
        "status": run.status,
        "name": run.name,
        "stages": merge_stage_results(run.stages or [], run.stage_results or {}),
        "stage_results": run.stage_results or {},
    }


@router.get("/project/{project_id}/bootstrap-data")
async def get_bootstrap_data(project_id: str, db: Session = Depends(get_db)):
    """获取 bootstrap 产出的"设定文档"（按 stage 整理成结构化视图，给"设定预览"面板用）

    返回：
      - project_meta:     4 必填 + 8 选填（从 _meta.user_input 读）
      - base:             基础外推（total_chapters / est_total_words / ai_removal / rationale）
      - theme:            主旨 + 基调
      - style:            文风 + 节奏
      - world:            世界观条目（按 category 分组）
      - characters:       主角 + 反派 + 配角（含 profile、relations）
      - arcs:             角色弧光
      - outline:          项目大纲（plot_lines / structure / pacing_notes）
      - foreshadowings:   伏笔列表（按短/中/长周期分组）
      - chapter_outlines: 章节细纲（数组）
      - run_status:       最新 run 的状态 + 时间戳
    """
    run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.project_id == project_id)
        .order_by(WorkflowRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="No run found for this project")

    sr = dict(run.stage_results or {})

    # 读 _meta.user_input（兼容老 run：可能缺失或为反推值）
    meta = sr.get("_meta", {})
    user_input = meta.get("user_input", {}) or {}
    project_meta = {
        "title": user_input.get("title", ""),
        "description": user_input.get("description", ""),
        "chapter_word_count": user_input.get("chapter_word_count", 0),
        "genre": user_input.get("genre", ""),
        # 8 选填
        "theme_input": user_input.get("theme", ""),
        "tone": user_input.get("tone", ""),
        "style_input": user_input.get("style", ""),
        "pacing": user_input.get("pacing", ""),
        "premise": user_input.get("premise", ""),
        "protagonist_input": user_input.get("protagonist", ""),
        "antagonist_input": user_input.get("antagonist", ""),
        "supporting_input": user_input.get("supporting", ""),
        "notes": user_input.get("notes", ""),
    }

    # 各 stage 的 data（如果 stage ok，data 是 dict；user_filled 时从 user_values 读）
    def _data(stage_id: str) -> dict | None:
        s = sr.get(stage_id) or {}
        status = s.get("status")
        if status == "ok":
            return s.get("data") or {}
        if status == "user_filled":
            # user_filled 时把 user_values 包装成 data 形态（让下游按 dict 处理）
            return s.get("user_values") or {}
        return None

    # ── 基础外推（stage_1） ──
    base = _data("stage_1_base") or {}

    # ── 主旨 / 基调（stage_2a） ──
    theme_data = _data("stage_2a_theme") or {}

    # ── 文风 / 节奏（stage_2b） ──
    style_data = _data("stage_2b_style") or {}

    # ── 世界观（stage_2c）：按 category 分组 ──
    #     修复：之前只读 status=="ok"，导致用户填了 premise 时（status=="user_filled"）返回空
    world_data = _data("stage_2c_world") or {}
    world_entries = world_data.get("world_entries", [])
    # 兜底：user_filled 时把 premise 包装成单个 world_entries（与 commit 时写入 WorldEntry 的格式一致）
    if not world_entries and world_data.get("premise"):
        world_entries = [{
            "category": "背景设定",
            "title": "世界观背景",
            "content": world_data["premise"],
            "tags": [],
        }]
    world_by_category: dict[str, list] = {}
    for entry in world_entries:
        cat = entry.get("category", "其他")
        world_by_category.setdefault(cat, []).append(entry)

    # ── 角色（stage_3a/3b/3c）──
    protagonist = _data("stage_3a_protagonist") or {}
    antagonist = _data("stage_3b_antagonist") or {}
    supporting_data = _data("stage_3c_supporting") or {}
    supporting = supporting_data.get("supporting", [])
    relations = supporting_data.get("relations", [])

    # ── 角色弧光（stage_3d）──
    arcs_data = _data("stage_3d_arcs") or {}
    arcs = arcs_data.get("arcs", [])

    # ── 项目大纲（stage_4a 架构 + stage_4a_chapter_outlines 拆分后）──
    outline_data = _data("stage_4a_outline") or {}
    # 兼容：之前没有 chapter_outlines 字段（早期版本）
    chapter_outlines = outline_data.get("chapter_outlines", []) if isinstance(outline_data, dict) else []
    # 新版：拆出后 chapter_outlines 走 stage_4a_chapter_outlines,且落地到 ProjectOutline.chapter_outlines 列
    extra_data = _data("stage_4a_chapter_outlines") or {}
    if extra_data.get("chapter_outlines"):
        chapter_outlines = list(extra_data["chapter_outlines"])
    # 如果 run.stage_results 缺(已 committed 跑过),从 ProjectOutline 表读
    if not chapter_outlines:
        from storage.models import ProjectOutline as _PO
        po_row = db.query(_PO).filter(_PO.project_id == project_id).first()
        if po_row and po_row.chapter_outlines:
            chapter_outlines = list(po_row.chapter_outlines)
    # 确保 outline 字段也带 chapter_outlines（前端用 bootstrapData.outline.chapter_outlines 访问）
    if isinstance(outline_data, dict):
        outline_data.setdefault("chapter_outlines", chapter_outlines)

    # ── 伏笔（stage_4b）：按 type/周期分组 ──
    # 实际数据结构：{"title", "content", "type": "短/中/长" 或 "short/medium/long", "suggested_plant_chapter", "suggested_resolve_chapter"}
    f_data = _data("stage_4b_foreshadow") or {}
    foreshadowings = f_data.get("foreshadowings", [])
    foreshadow_by_period: dict[str, list] = {
        "短周期": [], "中周期": [], "长周期": [], "未分类": [],
    }
    # 兼容多种字段命名 + 中英文值
    period_field_candidates = ["type", "period", "duration", "category"]
    period_value_map = {
        "short": "短周期", "medium": "中周期", "long": "长周期",
        "短": "短周期", "中": "中周期", "长": "长周期",
        "短周期": "短周期", "中周期": "中周期", "长周期": "长周期",
    }
    for f in foreshadowings:
        period = "未分类"
        for field in period_field_candidates:
            raw = f.get(field, "")
            if isinstance(raw, str) and raw in period_value_map:
                period = period_value_map[raw]
                break
        foreshadow_by_period[period].append(f)

    # ── 章节细纲（兼容旧版 stage_5_chapters，新版走 stage_4a 的 chapter_outlines）──
    chap_data = _data("stage_5_chapters") or {}
    legacy_chapter_outlines = chap_data.get("chapter_outlines", [])
    if not chapter_outlines:
        chapter_outlines = legacy_chapter_outlines

    return {
        "project_id": project_id,
        "run_id": run.id,
        "run_status": run.status,
        "run_created_at": run.created_at,
        "run_updated_at": run.updated_at,
        "project_meta": project_meta,
        "base": {
            "total_chapters": base.get("total_chapters"),
            "est_total_words": base.get("est_total_words"),
            "ai_removal": base.get("ai_removal"),
            "rationale": base.get("rationale", ""),
        },
        "theme": {
            "theme": theme_data.get("theme", ""),
            "tone": theme_data.get("tone", ""),
        },
        "style": {
            "style": style_data.get("style", ""),
            "pacing": style_data.get("pacing", ""),
        },
        "world": {
            "entries_by_category": world_by_category,
            "entry_count": len(world_entries),
        },
        "characters": {
            "protagonist": protagonist,
            "antagonist": antagonist,
            "supporting": supporting,
            "relations": relations,
        },
        "arcs": arcs,
        "outline": outline_data,
        "foreshadowings": {
            "by_period": foreshadow_by_period,
            "total": len(foreshadowings),
        },
        "chapter_outlines": chapter_outlines,
    }


@router.post("/run/{run_id}/rerun")
async def rerun_stage(run_id: int, req: RerunRequest, db: Session = Depends(get_db)):
    """重新跑某个 stage（异步：提交到线程池，立即返回 task_id）

    前端拿到 task_id 后轮询 /api/tasks/{task_id} 获取结果。
    """
    from llm.workflow import rerun_stage as _rerun
    from api.tasks import submit_llm_task, get_task

    # 防并发：同一 run 已有一个 rerun 任务在跑 → 拒绝新的请求
    if not _acquire_run_lock(run_id):
        raise HTTPException(
            status_code=409,
            detail="该 run 已有重跑任务在执行中，请等待当前任务完成后再试",
        )

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        _release_run_lock(run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "committed":
        _release_run_lock(run_id)
        raise HTTPException(
            status_code=400,
            detail="已 commit 的 run 不能 rerun stage，请新建项目或清除 commit 状态",
        )

    logger.info(f"[Workflow] rerun (async) run={run_id} stage={req.stage_id}")

    # 异步提交：在线程池里跑 LLM，主线程立即返回
    def _async_rerun_task(task_id: str, **kwargs):
        from storage.database import SessionLocal
        from api.tasks import _refresh_inmem_task_from_run

        run_id = kwargs["run_id"]
        stage_id = kwargs["stage_id"]

        # 重新开一个 session（线程池不能共用主线程的 db）
        local_db = SessionLocal()
        try:
            result = _rerun(run_id, stage_id, local_db)
            task = get_task(task_id)
            if task is None:
                return
            if result.get("status") == "ok":
                task.status = "completed"
                task.result = result
                task.progress = 100
                # 同步 in-memory task → DB
                _refresh_inmem_task_from_run(run_id)
            else:
                task.status = "failed"
                task.error = result.get("error", "rerun failed")
            task.completed_at = __import__("time").time()
            logger.info(f"[Workflow] async rerun done run={run_id} stage={stage_id} status={task.status}")
        except Exception as e:
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = __import__("time").time()
            logger.error(f"[Workflow] async rerun EXC run={run_id} stage={stage_id}: {e}", exc_info=True)
        finally:
            local_db.close()
            _release_run_lock(run_id)  # 无论成败都释放锁

    task = submit_llm_task(
        task_type="rerun_stage",
        llm_call_fn=_async_rerun_task,
        project_id=run.project_id,
        description=f"重跑 stage [{req.stage_id}]",
        run_id=run_id,
        stage_id=req.stage_id,
    )
    return {
        "status": "submitted",
        "task_id": task.id,
        "run_id": run_id,
        "stage_id": req.stage_id,
        "message": "rerun 已提交，立即返回；前端轮询 /api/tasks/{task_id} 拿结果",
    }


@router.post("/run/{run_id}/rerun-all")
async def rerun_all_stages(run_id: int, db: Session = Depends(get_db), force_all: bool = False):
    """重跑 run 中所有 stage（异步：提交到线程池，立即返回 task_id）

    行为：
      force_all=False（默认）：只重跑 failed / cancelled / 未开始的 stage，已成功的不动。
      force_all=True：重跑全部 stage（包括已成功的），仅 user_filled 和 skipped 不动。

    前端轮询 /api/tasks/{task_id} 拿结果。
    """
    from llm.workflow import rerun_all_failed_stages
    from api.tasks import submit_llm_task, get_task

    # 防并发：同一 run 已有一个 rerun-all 任务在跑 → 拒绝
    if not _acquire_run_lock(run_id):
        raise HTTPException(
            status_code=409,
            detail="该 run 已有重跑任务在执行中，请等待当前任务完成后再试",
        )

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        _release_run_lock(run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "committed":
        _release_run_lock(run_id)
        raise HTTPException(
            status_code=400,
            detail="已 commit 的 run 不能 rerun-all",
        )

    logger.info(f"[Workflow] rerun-all (async) run={run_id} force_all={force_all}")

    def _async_rerun_all_task(task_id: str, **kwargs):
        from storage.database import SessionLocal
        from api.tasks import _refresh_inmem_task_from_run
        import time as _time

        run_id = kwargs["run_id"]
        force_all = kwargs.get("force_all", False)
        local_db = SessionLocal()
        try:
            # 让前端能看到 stage 状态在变：把 run 标 running
            local_run = local_db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            if local_run and local_run.status in ("completed", "partial", "failed", "cancelled"):
                local_run.status = "running"
                local_db.commit()

            result = rerun_all_failed_stages(run_id, local_db, force_all=force_all)

            task = get_task(task_id)
            if task is None:
                return
            task.status = "completed" if result.get("status") == "ok" else "failed"
            task.result = result
            task.progress = 100
            task.completed_at = _time.time()
            # 同步 in-memory → DB
            synced = _refresh_inmem_task_from_run(run_id)
            result["in_mem_synced"] = synced
            logger.info(
                f"[Workflow] async rerun-all done run={run_id} "
                f"force_all={force_all} "
                f"rerun={len(result.get('rerun_stages', []))} "
                f"still_failed={len(result.get('still_failed', []))}"
            )
        except Exception as e:
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = __import__("time").time()
            logger.error(f"[Workflow] async rerun-all EXC run={run_id}: {e}", exc_info=True)
        finally:
            local_db.close()
            _release_run_lock(run_id)  # 无论成败都释放锁

    task = submit_llm_task(
        task_type="rerun_all",
        llm_call_fn=_async_rerun_all_task,
        project_id=run.project_id,
        description="重跑全部 stage" if force_all else "重跑失败/未完成 stage",
        run_id=run_id,
        force_all=force_all,
    )
    return {
        "status": "submitted",
        "task_id": task.id,
        "run_id": run_id,
        "force_all": force_all,
        "message": "rerun-all 已提交，立即返回；前端轮询 /api/tasks/{task_id} 拿结果，"
                   "并通过 /api/workflow/run/{run_id} 看 stage 状态变化",
    }


@router.post("/run/{run_id}/commit", response_model=CommitResponse)
async def commit_run(run_id: int, db: Session = Depends(get_db)):
    """把 stage_results 事务写入 DB（用于 auto_commit=false 时的手动提交）"""
    from llm.workflow import commit_bootstrap

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "committed":
        return CommitResponse(status="already_committed")

    if run.status not in ("completed", "partial"):
        raise HTTPException(
            status_code=400,
            detail=f"Run status is '{run.status}', cannot commit. Please ensure all stages succeeded.",
        )

    logger.info(f"[Workflow] commit run={run_id} project={run.project_id}")
    result = commit_bootstrap(run.project_id, run_id, db)
    return CommitResponse(
        status=result.get("status", "failed"),
        summary=result.get("summary", {}),
        error=result.get("error"),
    )


@router.post("/project/{project_id}/extend-outline")
async def extend_outline_chapters(
    project_id: str,
    target_chapters: int,
    extend_architecture: bool = True,
    db: Session = Depends(get_db),
):
    """大纲扩写/缩减:在已有 chapter_outlines 基础上变更到 target_chapters 章。

    支持 3 种情形:
      1. 扩写 (target > existing): 新增 chapter_outlines + 可选扩架构层
      2. 无变化 (target == existing): 直接返回
      3. 缩减 (target < existing): 删尾部章节(不删 Chapter,只删 chapter_outlines 元数据 + 失效伏笔)

    异步模式: 立即返回 task_id,前端轮询 /api/tasks/{task_id} 获取进度与结果。
    """
    from llm.workflow import extend_outline_chapters as _extend
    from api.tasks import submit_llm_task, get_task
    from storage.database import SessionLocal

    if target_chapters < 0:
        return {"status": "failed", "error": "target_chapters 必须 >= 0"}

    # 查项目元信息(用于任务描述)
    from storage.models.project import Project
    proj = db.query(Project).filter(Project.id == project_id).first()
    proj_title = proj.title if proj else f"#{project_id}"

    # 计算"扩"或"缩"方向用于任务描述
    from storage.models import ProjectOutline
    proj_outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    existing_max = 0
    if proj_outline and proj_outline.chapter_outlines:
        existing_max = max(
            [int(c.get("chapter_num", 0)) for c in proj_outline.chapter_outlines if c.get("chapter_num")],
            default=0,
        )
    if target_chapters > existing_max:
        action = "扩写"
        diff = target_chapters - existing_max
    elif target_chapters < existing_max:
        action = "缩减"
        diff = existing_max - target_chapters
    else:
        action = "无变化"
        diff = 0
    description = f"大纲{action} [{proj_title}] {existing_max}→{target_chapters} 章"
    if action == "无变化":
        # 直接同步返回(不进入线程池)
        result = _extend(
            project_id=project_id, target_total=target_chapters, db=db,
            extend_architecture=extend_architecture,
        )
        return result

    # 异步: 提交到线程池
    def _async_extend_task(task_id: str, **kwargs):
        local_db = SessionLocal()
        try:
            task = get_task(task_id)
            # project_id 不在 kwargs 里(被 submit_llm_task 的 named param 收走)
            # 从 task 对象取
            pid = task.project_id if task is not None else kwargs.get("project_id")
            target = kwargs.get("target_chapters") or kwargs.get("target_total")
            ext_arch = kwargs.get("extend_architecture", True)
            if task is not None:
                task.progress = 10
                task.status = "running"

            result = _extend(
                project_id=pid,
                target_total=target,
                db=local_db,
                extend_architecture=ext_arch,
            )
            task = get_task(task_id)
            if task is None:
                return
            if result.get("status") == "ok":
                task.status = "completed"
                task.result = result
                task.progress = 100
            else:
                task.status = "failed"
                task.error = result.get("error", "extend failed")
                task.result = result
        except Exception as e:
            logger.error(f"[extend-outline async] failed: {e}")
            task = get_task(task_id)
            if task is not None:
                task.status = "failed"
                task.error = str(e)
        finally:
            local_db.close()

    task = submit_llm_task(
        task_type="extend_outline",
        llm_call_fn=_async_extend_task,
        project_id=project_id,
        description=description,
        target_chapters=target_chapters,
        extend_architecture=extend_architecture,
    )
    return {
        "status": "submitted",
        "task_id": task.id,
        "description": description,
        "action": action,
        "old_total": existing_max,
        "target_total": target_chapters,
        "diff": diff,
        "message": f"已提交{action}任务,前端轮询 /api/tasks/{task.id} 获取进度",
    }


@router.post("/run/{run_id}/rerun-and-commit")
async def rerun_and_commit(run_id: int, req: RerunRequest, db: Session = Depends(get_db)):
    """重跑 stage 后自动 commit（异步：立即返回 task_id）"""
    from api.tasks import submit_llm_task, get_task
    from llm.workflow import rerun_stage as _rerun, commit_bootstrap

    # 防并发：同 run 已有重跑/提交任务在跑 → 拒绝
    if not _acquire_run_lock(run_id):
        raise HTTPException(
            status_code=409,
            detail="该 run 已有重跑任务在执行中，请等待当前任务完成后再试",
        )

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        _release_run_lock(run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    def _async_rerun_and_commit_task(task_id: str, **kwargs):
        from storage.database import SessionLocal
        import time as _time

        run_id_inner = kwargs["run_id"]
        stage_id = kwargs["stage_id"]
        local_db = SessionLocal()
        try:
            # 取 run（在新 session 里）
            local_run = local_db.query(WorkflowRun).filter(WorkflowRun.id == run_id_inner).first()
            if local_run is None:
                raise RuntimeError(f"Run {run_id_inner} not found")

            rerun_result = _rerun(run_id_inner, stage_id, local_db)
            if rerun_result.get("status") != "ok":
                task = get_task(task_id)
                if task:
                    task.status = "failed"
                    task.error = rerun_result.get("error", "rerun failed")
                    task.completed_at = _time.time()
                return

            commit_result = commit_bootstrap(local_run.project_id, run_id_inner, local_db)
            task = get_task(task_id)
            if task:
                task.status = "completed"
                task.result = {
                    "status": "committed",
                    "rerun_stage": stage_id,
                    "commit_summary": commit_result.get("summary", {}),
                }
                task.progress = 100
                task.completed_at = _time.time()
        except Exception as e:
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = _time.time()
            logger.error(f"[Workflow] async rerun-and-commit EXC run={run_id_inner}: {e}", exc_info=True)
        finally:
            local_db.close()
            _release_run_lock(run_id_inner)  # 无论成败都释放锁

    task = submit_llm_task(
        task_type="rerun_and_commit",
        llm_call_fn=_async_rerun_and_commit_task,
        project_id=run.project_id,
        description=f"重跑+commit stage [{req.stage_id}]",
        run_id=run_id,
        stage_id=req.stage_id,
    )
    return {
        "status": "submitted",
        "task_id": task.id,
        "run_id": run_id,
        "stage_id": req.stage_id,
        "message": "rerun-and-commit 已提交，立即返回；轮询 /api/tasks/{task_id} 拿结果",
    }
