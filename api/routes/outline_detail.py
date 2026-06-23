"""大纲 / 细纲 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import ProjectOutline, ChapterOutline, Project, Chapter
from datetime import datetime


router = APIRouter(prefix="/api/projects/{project_id}", tags=["大纲与细纲"])


# ─── Schemas ───

class PlotLine(BaseModel):
    title: str
    description: str = ""
    from_chapter: int = 1
    to_chapter: int = 1
    priority: int = 1


class ActSegment(BaseModel):
    name: str
    from_chapter: int
    to_chapter: int


class ProjectOutlineCreate(BaseModel):
    plot_lines: list[PlotLine] = []
    structure: dict = {}
    pacing_notes: str = ""
    outline_text: str = ""


class ProjectOutlineUpdate(BaseModel):
    plot_lines: list[PlotLine] | None = None
    structure: dict | None = None
    pacing_notes: str | None = None
    outline_text: str | None = None


class ProjectOutlineResponse(BaseModel):
    id: int
    project_id: str
    plot_lines: list
    structure: dict
    pacing_notes: str
    outline_text: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChapterOutlineCreate(BaseModel):
    chapter_id: int
    chapter_position: str = ""
    act_name: str = ""
    key_content: str = ""
    plot_advance: str = ""
    foreshadow_ids: list[int] = []
    foreshadow_notes: str = ""
    conflicts: list[dict] = []
    highlights: list[str] = []
    target_word_count: int = 0
    min_word_count: int = 0
    max_word_count: int = 0
    pacing: str = "平稳"
    character_ids: list[int] = []
    status: str = "planning"
    notes: str = ""
    qi_cheng_zhuan_he: dict = {}
    pacing_hooks: list = []
    reversals: list = []


class ChapterOutlineUpdate(BaseModel):
    chapter_position: str | None = None
    act_name: str | None = None
    key_content: str | None = None
    plot_advance: str | None = None
    foreshadow_ids: list[int] | None = None
    foreshadow_notes: str | None = None
    conflicts: list[dict] | None = None
    highlights: list[str] | None = None
    target_word_count: int | None = None
    min_word_count: int | None = None
    max_word_count: int | None = None
    pacing: str | None = None
    character_ids: list[int] | None = None
    status: str | None = None
    notes: str | None = None
    qi_cheng_zhuan_he: dict | None = None
    pacing_hooks: list | None = None
    reversals: list | None = None


class ChapterOutlineResponse(BaseModel):
    id: int
    chapter_id: int
    chapter_position: str
    act_name: str
    key_content: str
    plot_advance: str
    foreshadow_ids: list
    foreshadow_notes: str
    conflicts: list
    highlights: list
    target_word_count: int
    min_word_count: int
    max_word_count: int
    pacing: str
    character_ids: list
    status: str
    notes: str
    # 丰富结构（来自 chapter_outline_gen role 的 qi_cheng_zhuan_he 等输出）
    qi_cheng_zhuan_he: dict = {}
    pacing_hooks: list = []
    reversals: list = []
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Project Outline Routes ───

@router.get("/outline", response_model=ProjectOutlineResponse | None)
async def get_project_outline(project_id: str, db: Session = Depends(get_db)):
    """获取项目大纲（可能为空）"""
    outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    return outline


@router.post("/outline", response_model=ProjectOutlineResponse)
async def create_or_update_project_outline(
    project_id: str, data: ProjectOutlineCreate, db: Session = Depends(get_db)
):
    """创建或更新项目大纲（upsert）"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    if outline:
        # 更新
        for field in ["plot_lines", "structure", "pacing_notes", "outline_text"]:
            val = getattr(data, field, None)
            if val is not None:
                setattr(outline, field, val)
    else:
        outline = ProjectOutline(
            project_id=project_id,
            plot_lines=data.plot_lines,
            structure=data.structure,
            pacing_notes=data.pacing_notes,
            outline_text=data.outline_text,
        )
        db.add(outline)

    db.commit()
    db.refresh(outline)
    return outline


@router.put("/outline", response_model=ProjectOutlineResponse)
async def update_project_outline(
    project_id: str, data: ProjectOutlineUpdate, db: Session = Depends(get_db)
):
    """部分更新项目大纲"""
    outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found, use POST to create")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(outline, field, value)
    db.commit()
    db.refresh(outline)
    return outline


@router.delete("/outline")
async def delete_project_outline(project_id: str, db: Session = Depends(get_db)):
    outline = db.query(ProjectOutline).filter(ProjectOutline.project_id == project_id).first()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    db.delete(outline)
    db.commit()
    return {"status": "ok"}


# ─── Chapter Outline Routes ───

@router.get("/chapters/{chapter_id}/outline", response_model=ChapterOutlineResponse | None)
async def get_chapter_outline(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    """获取章节细纲"""
    # 隔离验证
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    outline = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).first()
    return outline


@router.post("/chapters/{chapter_id}/outline", response_model=ChapterOutlineResponse)
async def create_or_update_chapter_outline(
    project_id: str, chapter_id: int, data: ChapterOutlineCreate, db: Session = Depends(get_db)
):
    """创建或更新章节细纲（upsert）"""
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.project_id == project_id).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    outline = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).first()
    if outline:
        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "chapter_id":
                continue
            setattr(outline, field, value)
    else:
        outline = ChapterOutline(
            chapter_id=chapter_id,
            chapter_position=data.chapter_position,
            act_name=data.act_name,
            key_content=data.key_content,
            plot_advance=data.plot_advance,
            foreshadow_ids=data.foreshadow_ids,
            foreshadow_notes=data.foreshadow_notes,
            conflicts=data.conflicts,
            highlights=data.highlights,
            target_word_count=data.target_word_count,
            min_word_count=data.min_word_count,
            max_word_count=data.max_word_count,
            pacing=data.pacing,
            character_ids=data.character_ids,
            status=data.status,
            notes=data.notes,
            qi_cheng_zhuan_he=data.qi_cheng_zhuan_he,
            pacing_hooks=data.pacing_hooks,
            reversals=data.reversals,
        )
        db.add(outline)

    db.commit()
    db.refresh(outline)
    return outline


@router.put("/chapters/{chapter_id}/outline", response_model=ChapterOutlineResponse)
async def update_chapter_outline(
    project_id: str, chapter_id: int, data: ChapterOutlineUpdate, db: Session = Depends(get_db)
):
    """部分更新章节细纲"""
    # 隔离验证
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    outline = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).first()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(outline, field, value)
    db.commit()
    db.refresh(outline)
    return outline


@router.delete("/chapters/{chapter_id}/outline")
async def delete_chapter_outline(project_id: str, chapter_id: int, db: Session = Depends(get_db)):
    # 隔离验证
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    outline = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == chapter_id).first()
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found")
    db.delete(outline)
    db.commit()
    return {"status": "ok"}


# ─── 批量获取章节细纲 ───

@router.get("/chapter-outlines", response_model=list[ChapterOutlineResponse])
async def list_chapter_outlines(project_id: str, db: Session = Depends(get_db)):
    """获取项目下所有章节的细纲"""
    chapters = db.query(Chapter).filter(Chapter.project_id == project_id).order_by(Chapter.order).all()
    outlines = []
    for ch in chapters:
        outline = db.query(ChapterOutline).filter(ChapterOutline.chapter_id == ch.id).first()
        if outline:
            outlines.append(outline)
    return outlines
