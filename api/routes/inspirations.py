"""灵感管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Inspiration, Project


router = APIRouter(prefix="/api/projects/{project_id}/inspirations", tags=["灵感"])


# ─── Schemas ───

class InspirationCreate(BaseModel):
    content: str
    tags: list[str] = []
    source: str = ""
    related_characters: list[int] = []
    related_chapters: list[int] = []


class InspirationUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    source: str | None = None
    related_characters: list[int] | None = None
    related_chapters: list[int] | None = None


class InspirationResponse(BaseModel):
    id: int
    project_id: int
    content: str
    tags: list
    source: str
    related_characters: list
    related_chapters: list
    created_at: object
    updated_at: object

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[InspirationResponse])
async def list_inspirations(project_id: int, tag: str | None = None, db: Session = Depends(get_db)):
    """获取项目下所有灵感，支持按标签筛选"""
    query = db.query(Inspiration).filter(Inspiration.project_id == project_id)
    if tag:
        query = query.filter(Inspiration.tags.contains([tag]))
    return query.order_by(Inspiration.created_at.desc()).all()


@router.post("", response_model=InspirationResponse)
async def create_inspiration(project_id: int, data: InspirationCreate, db: Session = Depends(get_db)):
    """创建灵感"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    insp = Inspiration(
        project_id=project_id,
        content=data.content,
        tags=data.tags,
        source=data.source,
        related_characters=data.related_characters,
        related_chapters=data.related_chapters,
    )
    db.add(insp)
    db.commit()
    db.refresh(insp)
    return insp


@router.put("/{insp_id}", response_model=InspirationResponse)
async def update_inspiration(project_id: int, insp_id: int, data: InspirationUpdate, db: Session = Depends(get_db)):
    """更新灵感"""
    insp = db.query(Inspiration).filter(
        Inspiration.id == insp_id,
        Inspiration.project_id == project_id,
    ).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(insp, field, value)
    db.commit()
    db.refresh(insp)
    return insp


@router.delete("/{insp_id}")
async def delete_inspiration(project_id: int, insp_id: int, db: Session = Depends(get_db)):
    """删除灵感"""
    insp = db.query(Inspiration).filter(
        Inspiration.id == insp_id,
        Inspiration.project_id == project_id,
    ).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Inspiration not found")
    db.delete(insp)
    db.commit()
    return {"status": "ok"}


@router.get("/tags")
async def list_all_tags(project_id: int, db: Session = Depends(get_db)):
    """获取项目下所有标签（去重）"""
    inspirations = db.query(Inspiration).filter(
        Inspiration.project_id == project_id
    ).all()
    tags = set()
    for insp in inspirations:
        for tag in (insp.tags or []):
            tags.add(tag)
    return sorted(tags)
