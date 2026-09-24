"""分镜稿 CRUD API

场景级列表与生成在 api/routes/screenplays.py（GET /{sid}/storyboards、
POST /{sid}/storyboards/generate），此处补齐手动增删改与项目级列表。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project
from storage.models.screenplay import Screenplay, Storyboard


router = APIRouter(prefix="/api/projects/{project_id}", tags=["分镜稿"])


# ─── Schemas ───

class StoryboardResponse(BaseModel):
    id: int
    screenplay_id: int
    project_id: str
    shot_number: int
    shot_type: str
    camera_angle: str
    camera_movement: str
    duration_estimate: str
    location: str
    characters: list
    visual_description: str
    dialogue: str
    sound_effects: str
    notes: str

    class Config:
        from_attributes = True


class StoryboardCreate(BaseModel):
    shot_number: int = 1
    shot_type: str = "中景"
    camera_angle: str = "平视"
    camera_movement: str = "固定"
    duration_estimate: str = "3-5秒"
    location: str = ""
    characters: list = []
    visual_description: str = ""
    dialogue: str = ""
    sound_effects: str = ""
    notes: str = ""


class StoryboardUpdate(BaseModel):
    shot_number: int | None = None
    shot_type: str | None = None
    camera_angle: str | None = None
    camera_movement: str | None = None
    duration_estimate: str | None = None
    location: str | None = None
    characters: list | None = None
    visual_description: str | None = None
    dialogue: str | None = None
    sound_effects: str | None = None
    notes: str | None = None


# ─── Routes ───

@router.get("/storyboards", response_model=list[StoryboardResponse])
async def list_project_storyboards(
    project_id: str,
    screenplay_id: int | None = None,
    db: Session = Depends(get_db),
):
    """项目级分镜列表，可选按场景过滤"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    query = db.query(Storyboard).filter(Storyboard.project_id == project_id)
    if screenplay_id is not None:
        query = query.filter(Storyboard.screenplay_id == screenplay_id)
    return query.order_by(Storyboard.screenplay_id, Storyboard.shot_number).all()


@router.post("/screenplays/{screenplay_id}/storyboards", response_model=StoryboardResponse)
async def create_storyboard(
    project_id: str,
    screenplay_id: int,
    data: StoryboardCreate,
    db: Session = Depends(get_db),
):
    """手动新增一个分镜"""
    screenplay = db.query(Screenplay).filter(
        Screenplay.id == screenplay_id,
        Screenplay.project_id == project_id,
    ).first()
    if not screenplay:
        raise HTTPException(status_code=404, detail="Screenplay not found")

    storyboard = Storyboard(
        screenplay_id=screenplay_id,
        project_id=project_id,
        shot_number=data.shot_number,
        shot_type=data.shot_type,
        camera_angle=data.camera_angle,
        camera_movement=data.camera_movement,
        duration_estimate=data.duration_estimate,
        location=data.location or screenplay.location or "",
        characters=data.characters or screenplay.characters_present or [],
        visual_description=data.visual_description,
        dialogue=data.dialogue,
        sound_effects=data.sound_effects,
        notes=data.notes,
    )
    db.add(storyboard)
    db.commit()
    db.refresh(storyboard)
    return storyboard


@router.put("/storyboards/{storyboard_id}", response_model=StoryboardResponse)
async def update_storyboard(
    project_id: str,
    storyboard_id: int,
    data: StoryboardUpdate,
    db: Session = Depends(get_db),
):
    """更新分镜（部分字段）"""
    storyboard = db.query(Storyboard).filter(
        Storyboard.id == storyboard_id,
        Storyboard.project_id == project_id,
    ).first()
    if not storyboard:
        raise HTTPException(status_code=404, detail="Storyboard not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        # characters 是普通 JSON 列（未包 Mutable），必须赋新对象才会被检测到
        if field == "characters":
            value = list(value)
        setattr(storyboard, field, value)

    db.commit()
    db.refresh(storyboard)
    return storyboard


@router.delete("/storyboards/{storyboard_id}")
async def delete_storyboard(
    project_id: str,
    storyboard_id: int,
    db: Session = Depends(get_db),
):
    """删除分镜"""
    storyboard = db.query(Storyboard).filter(
        Storyboard.id == storyboard_id,
        Storyboard.project_id == project_id,
    ).first()
    if not storyboard:
        raise HTTPException(status_code=404, detail="Storyboard not found")

    db.delete(storyboard)
    db.commit()
    return {"detail": "Deleted"}
