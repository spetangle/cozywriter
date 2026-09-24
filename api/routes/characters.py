"""角色管理 API"""
import time

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
    appearance: dict = {}
    appearance_changes: list = []


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    profile: dict | None = None
    description: str | None = None
    avatar: str | None = None
    appearance: dict | None = None
    appearance_changes: list | None = None


class CharacterResponse(BaseModel):
    id: int
    project_id: str
    name: str
    role: str
    profile: dict
    description: str
    avatar: str
    appearance: dict = {}
    appearance_changes: list = []
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
        appearance=data.appearance,
        appearance_changes=data.appearance_changes,
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
    if data.appearance is not None:
        character.appearance = data.appearance
    if data.appearance_changes is not None:
        character.appearance_changes = data.appearance_changes

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


@router.post("/{character_id}/generate-appearance")
async def generate_appearance(project_id: str, character_id: int, db: Session = Depends(get_db)):
    """AI 生成角色外貌草稿（异步任务）

    只返回生成结果，不直接落库 —— 前端填入草稿供用户审阅/修改后，
    再通过 PUT /characters/{id} 的 appearance 字段保存。
    """
    from api.tasks import submit_llm_task

    character = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    def _async_appearance_task(task_id: str, _project_id: str, _character_id: int, _ctx: dict):
        from storage.database import SessionLocal
        from llm.script_pipeline import _call_llm, _parse_json
        from storage.models import Character as _Character

        _db = SessionLocal()
        try:
            from api.tasks import get_task
            task = get_task(task_id)
            if not task:
                return

            raw = _call_llm(
                "script_appearance_gen", _ctx,
                f"请为角色「{_ctx['character_name']}」设计详细外貌。",
                db=_db, project_id=_project_id, task_id=task_id,
            )
            parsed = _parse_json(raw)
            appearance = {}
            if isinstance(parsed, dict):
                inner = parsed.get("appearance")
                appearance = inner if isinstance(inner, dict) else parsed
            if not isinstance(appearance, dict) or not appearance:
                task.status = "failed"
                task.error = "未能从模型输出中解析出外貌 JSON"
                task.completed_at = time.time()
                return

            char = _db.query(_Character).filter(_Character.id == _character_id).first()
            task.result = {"appearance": appearance, "character_name": char.name if char else ""}
            task.status = "completed"
            task.progress = 100
            task.completed_at = time.time()
        except Exception as e:
            from api.tasks import get_task
            task = get_task(task_id)
            if task:
                task.status = "failed"
                task.error = str(e)
                task.completed_at = time.time()
        finally:
            _db.close()

    ctx = {
        "script_format": project.script_format or "movie",
        "character_name": character.name,
        "character_role": character.role or "配角",
        "character_description": character.description or "（暂无描述）",
        "project_description": project.description or "（暂无背景）",
    }

    task = submit_llm_task(
        task_type="generate_appearance",
        llm_call_fn=_async_appearance_task,
        project_id=project_id,
        description=f"生成角色外貌「{character.name}」",
        _project_id=project_id,
        _character_id=character_id,
        _ctx=ctx,
    )
    return {"task_id": task.id, "status": "submitted"}


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
