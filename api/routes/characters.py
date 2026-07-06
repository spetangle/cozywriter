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
    """删除角色（仅允许删除无剧情关联的角色）"""
    from storage.models import Chapter, PlotPoint, Foreshadowing
    
    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    references_count = 0
    
    chapters = db.query(Chapter).filter(Chapter.project_id == project_id).all()
    for ch in chapters:
        if ch.content and character.name in ch.content:
            references_count += 1
    
    plot_points = db.query(PlotPoint).filter(PlotPoint.project_id == project_id).all()
    for pp in plot_points:
        content = pp.description or pp.title or ""
        if character.name in content:
            references_count += 1
    
    foreshadows = db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id).all()
    for fs in foreshadows:
        content = fs.content or fs.title or fs.connection_to_mainline or ""
        if character.name in content:
            references_count += 1
    
    if references_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该角色在剧情中出现 {references_count} 次，无法直接删除。请先使用替换角色功能清理关联内容。"
        )

    db.delete(character)
    db.commit()

    try:
        kb = KnowledgeBase()
        kb.delete_character(character_id)
    except Exception:
        pass

    return {"status": "ok"}


@router.get("/{character_id}/references")
async def get_character_references(project_id: str, character_id: str, db: Session = Depends(get_db)):
    """查找角色的关联信息（剧情点、伏笔、章节等）
    
    character_id 支持两种格式:
    - 数字ID: 数据库中的角色
    - ai-角色名: AI生成的角色
    """
    from storage.models import Chapter, PlotPoint, Foreshadowing
    
    character_name = ""
    
    if character_id.startswith("ai-"):
        character_name = character_id[3:]
    else:
        try:
            char_id = int(character_id)
            character = (
                db.query(Character)
                .filter(Character.id == char_id, Character.project_id == project_id)
                .first()
            )
            if not character:
                raise HTTPException(status_code=404, detail="角色不存在")
            character_name = character.name
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的角色ID")
    
    references = {
        "character_name": character_name,
        "chapters": [],
        "plot_points": [],
        "foreshadows": [],
        "total_count": 0,
    }
    
    chapters = db.query(Chapter).filter(Chapter.project_id == project_id).all()
    for ch in chapters:
        if ch.content and character_name in ch.content:
            references["chapters"].append({
                "id": ch.id,
                "order": ch.order,
                "title": ch.title,
                "match_count": ch.content.count(character_name),
            })
    
    plot_points = db.query(PlotPoint).filter(PlotPoint.project_id == project_id).all()
    for pp in plot_points:
        content = pp.description or pp.title or ""
        if character_name in content:
            references["plot_points"].append({
                "id": pp.id,
                "title": pp.title,
                "description": pp.description,
            })
    
    foreshadows = db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id).all()
    for fs in foreshadows:
        content = fs.content or fs.title or fs.connection_to_mainline or ""
        if character_name in content:
            references["foreshadows"].append({
                "id": fs.id,
                "title": fs.title,
                "description": fs.content,
            })
    
    references["total_count"] = len(references["chapters"]) + len(references["plot_points"]) + len(references["foreshadows"])
    
    return references
