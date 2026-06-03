"""工作流管理 API - 重跑 / 提交 / 状态查询"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models.workflow import WorkflowRun
from logger import logger


router = APIRouter(prefix="/api/workflow", tags=["工作流"])


# ─── Schemas ───

class RerunRequest(BaseModel):
    stage_id: str


class CommitResponse(BaseModel):
    status: str  # committed / failed / already_committed
    summary: dict = {}
    error: str | None = None


class WorkflowStatusResponse(BaseModel):
    run_id: int
    project_id: int
    name: str
    status: str
    current_stage_index: int
    stages: list[dict] = []
    stage_results: dict = {}
    created_at: object
    updated_at: object


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
            "stages": run.stages or [],
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
        stages=run.stages or [],
        stage_results=run.stage_results or {},
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/project/{project_id}/latest")
async def get_latest_run(project_id: int, db: Session = Depends(get_db)):
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
        "stages": run.stages or [],
        "stage_results": run.stage_results or {},
    }


@router.post("/run/{run_id}/rerun")
async def rerun_stage(run_id: int, req: RerunRequest, db: Session = Depends(get_db)):
    """重新跑某个 stage（覆盖之前的结果）"""
    from llm.workflow import rerun_stage as _rerun

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status == "committed":
        raise HTTPException(
            status_code=400,
            detail="已 commit 的 run 不能 rerun stage，请新建项目或清除 commit 状态",
        )

    logger.info(f"[Workflow] rerun run={run_id} stage={req.stage_id}")
    result = _rerun(run_id, req.stage_id, db)
    return result


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


@router.post("/run/{run_id}/rerun-and-commit")
async def rerun_and_commit(run_id: int, req: RerunRequest, db: Session = Depends(get_db)):
    """重跑 stage 后自动 commit（用于用户在预览页修改后提交）"""
    from llm.workflow import rerun_stage as _rerun, commit_bootstrap

    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    rerun_result = _rerun(run_id, req.stage_id, db)
    if rerun_result.get("status") != "ok":
        return {
            "status": "rerun_failed",
            "error": rerun_result.get("error"),
        }

    commit_result = commit_bootstrap(run.project_id, run_id, db)
    return {
        "status": "committed",
        "rerun_stage": req.stage_id,
        "commit_summary": commit_result.get("summary", {}),
    }
