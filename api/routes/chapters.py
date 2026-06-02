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
