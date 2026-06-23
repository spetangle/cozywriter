"""世界观管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import WorldEntry, Project
from rag.knowledge_base import KnowledgeBase
from datetime import datetime


router = APIRouter(prefix="/api/projects/{project_id}/worldbuilding", tags=["世界观"])


# ─── Schemas ───

class WorldEntryCreate(BaseModel):
    category: str
    title: str
    content: str = ""
    tags: list[str] = []


class WorldEntryUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


class WorldEntryResponse(BaseModel):
    id: int
    project_id: str
    category: str
    title: str
    content: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[WorldEntryResponse])
async def list_world_entries(project_id: str, category: str | None = None, db: Session = Depends(get_db)):
    """获取世界观条目列表"""
    query = db.query(WorldEntry).filter(WorldEntry.project_id == project_id)
    if category:
        query = query.filter(WorldEntry.category == category)
    entries = query.all()
    return entries


@router.post("", response_model=WorldEntryResponse)
async def create_world_entry(project_id: str, data: WorldEntryCreate, db: Session = Depends(get_db)):
    """创建世界观条目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    entry = WorldEntry(
        project_id=project_id,
        category=data.category,
        title=data.title,
        content=data.content,
        tags=data.tags,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # 索引到 RAG 知识库
    try:
        kb = KnowledgeBase()
        kb.add_world_entry(entry)
    except Exception:
        pass

    return entry


@router.put("/{entry_id}", response_model=WorldEntryResponse)
async def update_world_entry(
    project_id: str, entry_id: int, data: WorldEntryUpdate, db: Session = Depends(get_db)
):
    """更新世界观条目"""
    entry = (
        db.query(WorldEntry)
        .filter(WorldEntry.id == entry_id, WorldEntry.project_id == project_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="World entry not found")

    if data.category is not None:
        entry.category = data.category
    if data.title is not None:
        entry.title = data.title
    if data.content is not None:
        entry.content = data.content
    if data.tags is not None:
        entry.tags = data.tags

    db.commit()
    db.refresh(entry)

    # 更新 RAG 索引
    try:
        kb = KnowledgeBase()
        kb.update_world_entry(entry)
    except Exception:
        pass

    return entry


@router.delete("/{entry_id}")
async def delete_world_entry(project_id: str, entry_id: int, db: Session = Depends(get_db)):
    """删除世界观条目"""
    entry = (
        db.query(WorldEntry)
        .filter(WorldEntry.id == entry_id, WorldEntry.project_id == project_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="World entry not found")

    db.delete(entry)
    db.commit()

    # 从 RAG 知识库删除
    try:
        kb = KnowledgeBase()
        kb.delete_world_entry(entry_id)
    except Exception:
        pass

    return {"status": "ok"}
