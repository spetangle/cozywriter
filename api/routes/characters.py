"""角色管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Character, Project
from rag.knowledge_base import KnowledgeBase
from rag.embedder import LocalEmbedder
from datetime import datetime


router = APIRouter(prefix="/api/projects/{project_id}/characters", tags=["角色"])


# ─── Schemas ───

class CharacterCreate(BaseModel):
    name: str
    role: str = "配角"
    profile: dict = {}
    description: str = ""
    avatar: str = ""


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    profile: dict | None = None
    description: str | None = None
    avatar: str | None = None


class CharacterResponse(BaseModel):
    id: int
    project_id: str
    name: str
    role: str
    profile: dict
    description: str
    avatar: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[CharacterResponse])
async def list_characters(project_id: str, db: Session = Depends(get_db)):
    """获取项目下所有角色"""
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    return characters


@router.post("", response_model=CharacterResponse)
async def create_character(project_id: str, data: CharacterCreate, db: Session = Depends(get_db)):
    """创建角色"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    character = Character(
        project_id=project_id,
        name=data.name,
        role=data.role,
        profile=data.profile,
        description=data.description,
        avatar=data.avatar,
    )
    db.add(character)
    db.commit()
    db.refresh(character)

    # 索引到 RAG 知识库
    try:
        kb = KnowledgeBase()
        kb.add_character(character)
    except Exception:
        pass  # RAG 索引失败不影响主流程

    return character


@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(
    project_id: str, character_id: int, data: CharacterUpdate, db: Session = Depends(get_db)
):
    """更新角色"""
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if data.name is not None:
        character.name = data.name
    if data.role is not None:
        character.role = data.role
    if data.profile is not None:
        character.profile = data.profile
    if data.description is not None:
        character.description = data.description
    if data.avatar is not None:
        character.avatar = data.avatar

    db.commit()
    db.refresh(character)

    # 更新 RAG 索引
    try:
        kb = KnowledgeBase()
        kb.update_character(character)
    except Exception:
        pass

    return character


@router.delete("/{character_id}")
async def delete_character(project_id: str, character_id: int, db: Session = Depends(get_db)):
    """删除角色"""
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    db.delete(character)
    db.commit()

    # 从 RAG 知识库删除
    try:
        kb = KnowledgeBase()
        kb.delete_character(character_id)
    except Exception:
        pass

    return {"status": "ok"}
