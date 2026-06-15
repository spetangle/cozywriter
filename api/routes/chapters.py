"""章节管理 API - 严格项目隔离"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Chapter, ChapterVersion, Project
import re
from logger import logger



router = APIRouter(prefix="/api", tags=["章节"])


# ─── Schemas ───

class ChapterCreate(BaseModel):
    # 修复：project_id 改为可选（从 URL 路径中取，避免 422）
    # 之前这里必填， 但前端只发 {title, order}，后端验证 project_id 缺失 → 422
    project_id: int | None = None
    title: str
    order: int = 0
    content: str = ""
    synopsis: str = ""


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    synopsis: str | None = None
    order: int | None = None


class ChapterResponse(BaseModel):
    id: int
    project_id: int
    title: str
    order: int
    content: str
    word_count: int
    synopsis: str
    created_at: object
    updated_at: object

    class Config:
        from_attributes = True


class VersionResponse(BaseModel):
    id: int
    chapter_id: int
    content: str
    version_num: int
    created_at: object

    class Config:
        from_attributes = True


# ─── 隔离辅助 ───

def _verify_chapter(chapter_id: int, project_id: int, db: Session) -> Chapter:
    """验证章节属于指定项目，不属于则抛出 404"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


def _count_words(text: str) -> int:
    chinese = len(re.findall(r'[一-鿿]', text))
    english = len(re.findall(r'[a-zA-Z]+', text))
    return chinese + english


# ─── Routes ───

@router.get("/projects/{project_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(project_id: int, db: Session = Depends(get_db)):
    """获取项目下所有章节"""
    chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.order)
        .all()
    )
    return chapters


@router.post("/projects/{project_id}/chapters", response_model=ChapterResponse)
async def create_chapter(project_id: int, data: ChapterCreate, db: Session = Depends(get_db)):
    """创建章节"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    word_count = _count_words(data.content)
    chapter = Chapter(
        project_id=project_id,
        title=data.title,
        order=data.order,
        content=data.content,
        synopsis=data.synopsis,
        word_count=word_count,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


# ─── 跨项目隔离：chapter_id 必须带 project_id 验证 ───

@router.get("/projects/{project_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(project_id: int, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节详情（带项目隔离验证）"""
    chapter = _verify_chapter(chapter_id, project_id, db)
    return chapter


@router.put("/projects/{project_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(project_id: int, chapter_id: int, data: ChapterUpdate, db: Session = Depends(get_db)):
    """更新章节（自动创建版本快照）"""
    chapter = _verify_chapter(chapter_id, project_id, db)

    last_version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .first()
    )
    next_version_num = (last_version.version_num + 1) if last_version else 1
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        version_num=next_version_num,
    )
    db.add(version)

    if data.title is not None:
        chapter.title = data.title
    if data.synopsis is not None:
        chapter.synopsis = data.synopsis
    if data.order is not None:
        chapter.order = data.order
    if data.content is not None:
        chapter.content = data.content
        chapter.word_count = _count_words(data.content)

    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/projects/{project_id}/chapters/{chapter_id}")
async def delete_chapter(project_id: int, chapter_id: int, db: Session = Depends(get_db)):
    """删除章节"""
    chapter = _verify_chapter(chapter_id, project_id, db)
    db.delete(chapter)
    db.commit()
    return {"status": "ok"}


@router.get("/projects/{project_id}/chapters/{chapter_id}/versions", response_model=list[VersionResponse])
async def list_versions(project_id: int, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节版本历史"""
    _verify_chapter(chapter_id, project_id, db)
    versions = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .all()
    )
    return versions


@router.post("/projects/{project_id}/chapters/{chapter_id}/rollback/{version_num}", response_model=ChapterResponse)
async def rollback_chapter(project_id: int, chapter_id: int, version_num: int, db: Session = Depends(get_db)):
    """回滚到指定版本"""
    chapter = _verify_chapter(chapter_id, project_id, db)

    version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id, ChapterVersion.version_num == version_num)
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    last_version = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.version_num.desc())
        .first()
    )
    backup = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        version_num=last_version.version_num + 1,
    )
    db.add(backup)

    chapter.content = version.content
    chapter.word_count = _count_words(version.content)
    db.commit()
    db.refresh(chapter)
    return chapter


# ═══════════════════════════════════════════════════════════════
# 章节生成流水线 API
# ═══════════════════════════════════════════════════════════════

class PipelineRequest(BaseModel):
    project_id: int
    chapter_id: int
    provider: str | None = None
    auto_revise: bool = True
    revision_threshold: float = 6.5
    guide: str = ""  # 内容引导，用于在LLM生成细纲时引导情节走向


class PipelineResponse(BaseModel):
    status: str
    task_id: str | None = None
    run_id: int | None = None
    project_id: int | None = None
    chapter_id: int | None = None
    final_word_count: int | None = None
    stages: dict = {}
    post_processing: dict = {}
    error: str | None = None
    total_duration_ms: float | None = None
    notifications: list = []


# 复用此路由的 generator 路径
pipeline_router = APIRouter(prefix="/api/chapters", tags=["章节生成"])


@pipeline_router.post("/generate-pipeline", response_model=PipelineResponse)
async def run_pipeline(req: PipelineRequest, db: Session = Depends(get_db)):
    """
    一键章节生成（9 步流水线，异步：提交到线程池，立即返回 task_id）

    前端轮询 /api/tasks/{task_id} 获取结果。
    """
    from api.tasks import submit_llm_task
    task = submit_llm_task(
        task_type="chapter_pipeline",
        llm_call_fn=_async_pipeline_task,
        project_id=req.project_id,
        description=f"生成章节 [{req.chapter_id}]",
        req=req,
    )
    return PipelineResponse(
        status="submitted",
        task_id=task.id,
        project_id=req.project_id,
        chapter_id=req.chapter_id,
    )


def _async_pipeline_task(task_id: str, req: PipelineRequest):
    from storage.database import SessionLocal
    from llm.chapter_pipeline import run_chapter_generation_pipeline, PIPELINE_STAGES_META
    from api.tasks import get_task
    import time as _time

    db = SessionLocal()
    try:
        task = get_task(task_id)

        # 初始化 task.result.stages（让前端轮询时一开始就能看到 9 个 step 骨架）
        if task is not None:
            task.result = {
                "stages": {
                    m["id"]: {
                        "id": m["id"],
                        "label": m["label"],
                        "weight": m["weight"],
                        "status": "pending",  # pending / running / completed / failed
                        "duration_ms": None,
                    }
                    for m in PIPELINE_STAGES_META
                },
                "current_stage": None,
                "progress_pct": 0,
                "post_processing": {},
            }
            task.progress = 5  # 一启动就让任务管理面板活起来

        # 进度回调：每 stage 跑开始/完成时调用
        def _on_progress(stage_id: str, status: str, info: dict):
            t = get_task(task_id)
            if t is None:
                return
            r = dict(t.result or {})
            stages = dict(r.get("stages") or {})
            entry = dict(stages.get(stage_id) or {"id": stage_id})
            entry["status"] = status
            if "duration_ms" in info:
                entry["duration_ms"] = info["duration_ms"]
            if "label" in info:
                entry["label"] = info["label"]
            if "error" in info:
                entry["error"] = info["error"]
            if "score" in info:
                entry["score"] = info["score"]
            stages[stage_id] = entry
            r["stages"] = stages
            r["current_stage"] = stage_id if status == "running" else r.get("current_stage")
            r["progress_pct"] = info.get("progress_pct", r.get("progress_pct", 0))
            t.result = r
            t.progress = max(t.progress or 0, min(95, r["progress_pct"] + 5))
            logger.info(
                f"[PipelineTask {task_id}] stage {stage_id} → {status} "
                f"({entry.get('duration_ms') or 0:.0f}ms) progress={r['progress_pct']}%"
            )

        result = run_chapter_generation_pipeline(
            db, req.project_id, req.chapter_id, req.provider,
            auto_revise=req.auto_revise,
            revision_threshold=req.revision_threshold,
            progress_cb=_on_progress,
            guide=req.guide,
        )

        # 收尾：把完整 stages 列表 + 终态写进 task.result
        if task is not None:
            r = dict(task.result or {})
            r["status"] = result.get("status")
            r["final_word_count"] = result.get("final_word_count")
            r["post_processing"] = result.get("post_processing", {})
            r["total_duration_ms"] = result.get("total_duration_ms")
            r["error"] = result.get("error")
            r["progress_pct"] = 100
            task.result = r
            task.progress = 100
            task.completed_at = _time.time()
        return result
    finally:
        db.close()




# ═══════════════════════════════════════════════════════════════
# 章节修订 API（根据细纲和评审报告重新生成正文）
# ═══════════════════════════════════════════════════════════════

class ReviseRequest(BaseModel):
    project_id: int
    chapter_id: int
    provider: str | None = None


@pipeline_router.post("/revise", response_model=PipelineResponse)
async def revise_chapter(req: ReviseRequest, db: Session = Depends(get_db)):
    """
    章节修订：根据已生成的细纲和评审报告，由LLM重新生成正文。
    旧版正文标记为废稿，移入废纸篓。
    """
    from api.tasks import submit_llm_task

    # 验证章节存在且有正文
    chapter = db.query(Chapter).filter(Chapter.id == req.chapter_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    if not chapter.content:
        raise HTTPException(status_code=400, detail="章节没有正文内容，无法修订")

    task = submit_llm_task(
        task_type="chapter_revise",
        llm_call_fn=_async_revise_task,
        project_id=req.project_id,
        description=f"修订章节 [{req.chapter_id}]",
        req=req,
    )
    return PipelineResponse(
        status="submitted",
        task_id=task.id,
        project_id=req.project_id,
        chapter_id=req.chapter_id,
    )


def _async_revise_task(task_id: str, req: ReviseRequest):
    from storage.database import SessionLocal
    from llm.chapter_pipeline import run_chapter_revise

    db = SessionLocal()
    try:
        # 初始化 task.result.stages
        from api.tasks import get_task
        task = get_task(task_id)
        if task is not None:
            revise_stages = [
                "1_get_outline", "2_save_old", "3_get_review",
                "4_generate", "5_adjust", "6_review", "7_save", "8_post"
            ]
            task.result = {
                "stages": {
                    sid: {"id": sid, "label": sid, "status": "pending", "duration_ms": None}
                    for sid in revise_stages
                },
                "current_stage": None,
                "progress_pct": 0,
            }
            task.progress = 5

        # 进度回调
        def _on_progress(stage_id: str, status: str, info: dict):
            t = get_task(task_id)
            if t is None:
                return
            r = dict(t.result or {})
            stages = dict(r.get("stages") or {})
            entry = dict(stages.get(stage_id) or {"id": stage_id})
            entry["status"] = status
            if "duration_ms" in info:
                entry["duration_ms"] = info["duration_ms"]
            if "label" in info:
                entry["label"] = info["label"]
            if "error" in info:
                entry["error"] = info["error"]
            if "score" in info:
                entry["score"] = info["score"]
            stages[stage_id] = entry
            r["stages"] = stages
            r["current_stage"] = stage_id if status == "running" else r.get("current_stage")
            r["progress_pct"] = info.get("progress_pct", r.get("progress_pct", 0))
            t.result = r
            t.progress = max(t.progress or 0, min(95, r["progress_pct"] + 5))
            logger.info(
                f"[ReviseTask {task_id}] stage {stage_id} -> {status} "
                f"({entry.get('duration_ms') or 0:.0f}ms) progress={r['progress_pct']}%"
            )

        result = run_chapter_revise(
            db=db,
            project_id=req.project_id,
            chapter_id=req.chapter_id,
            provider=req.provider,
            task_id=task_id,
            progress_cb=_on_progress,
        )
        return result
    finally:
        db.close()
