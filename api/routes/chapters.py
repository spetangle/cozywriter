"""章节管理 API - 严格项目隔离"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Chapter, ChapterVersion, Project
import re


router = APIRouter(prefix="/api", tags=["章节"])


# ─── Schemas ───

class ChapterCreate(BaseModel):
    project_id: int
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
    from llm.chapter_pipeline import run_chapter_generation_pipeline
    from api.tasks import get_task

    db = SessionLocal()
    try:
        task = get_task(task_id)
        result = run_chapter_generation_pipeline(
            db, req.project_id, req.chapter_id, req.provider,
            auto_revise=req.auto_revise,
            revision_threshold=req.revision_threshold,
        )
        if task:
            task.result = {
                "final_word_count": result.get("final_word_count"),
                "stages": {k: v.get("status") for k, v in result.get("stages", {}).items()},
                "post_processing": result.get("post_processing", {}),
            }
        return result
    finally:
        db.close()
