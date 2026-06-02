"""主题/伏笔/角色弧光/一致性 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Theme, Foreshadowing, ConsistencyRecord, CharacterArc, CharacterRelation, Project, Character
from datetime import datetime


router = APIRouter(prefix="/api/projects/{project_id}", tags=["高级管理"])


# ─── Schemas ───

class ThemeCreate(BaseModel):
    theme_type: str
    title: str
    description: str = ""
    related_theme_ids: list[int] = []


class ThemeUpdate(BaseModel):
    theme_type: str | None = None
    title: str | None = None
    description: str | None = None
    related_theme_ids: list[int] | None = None


class ThemeResponse(BaseModel):
    id: int
    project_id: int
    theme_type: str
    title: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True


class ForeshadowingCreate(BaseModel):
    title: str
    content: str = ""
    plant_chapter_id: int | None = None
    plant_order: int = 0
    status: str = "active"


class ForeshadowingUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    resolve_chapter_id: int | None = None
    status: str | None = None


class ForeshadowingResponse(BaseModel):
    id: int
    project_id: int
    plant_chapter_id: int | None
    resolve_chapter_id: int | None
    title: str
    content: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConsistencyRecordCreate(BaseModel):
    entity_type: str
    entity_id: int
    property_name: str
    old_value: str = ""
    new_value: str = ""
    reason: str = ""
    chapter_id: int | None = None


class ConsistencyRecordUpdate(BaseModel):
    new_value: str | None = None
    reason: str | None = None
    is_consistent: bool | None = None
    inconsistency_note: str | None = None


class CharacterArcCreate(BaseModel):
    character_id: int
    arc_type: str
    start_state: str = ""
    end_state: str = ""
    current_state: str = ""
    key_behavior: str = ""


class CharacterArcUpdate(BaseModel):
    current_state: str | None = None
    key_behavior: str | None = None
    is_stable: bool | None = None


class CharacterRelationCreate(BaseModel):
    from_character_id: int
    to_character_id: int
    relation_type: str
    description: str = ""
    strength: int = 5
    chapter_id: int | None = None


class CharacterRelationUpdate(BaseModel):
    relation_type: str | None = None
    description: str | None = None
    strength: int | None = None
    status: str | None = None
    is_consistent: bool | None = None


# ─── Theme Routes ───

@router.get("/themes", response_model=list[ThemeResponse])
async def list_themes(project_id: int, db: Session = Depends(get_db)):
    return db.query(Theme).filter(Theme.project_id == project_id).all()


@router.post("/themes", response_model=ThemeResponse)
async def create_theme(project_id: int, data: ThemeCreate, db: Session = Depends(get_db)):
    theme = Theme(project_id=project_id, **data.model_dump())
    db.add(theme)
    db.commit()
    db.refresh(theme)
    return theme


@router.put("/themes/{theme_id}", response_model=ThemeResponse)
async def update_theme(project_id: int, theme_id: int, data: ThemeUpdate, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id, Theme.project_id == project_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(theme, key, value)
    db.commit()
    db.refresh(theme)
    return theme


@router.delete("/themes/{theme_id}")
async def delete_theme(project_id: int, theme_id: int, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id, Theme.project_id == project_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    db.delete(theme)
    db.commit()
    return {"status": "ok"}


# ─── Foreshadowing Routes ───

@router.get("/foreshadowings", response_model=list[ForeshadowingResponse])
async def list_foreshadowings(project_id: int, status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Foreshadowing).filter(Foreshadowing.project_id == project_id)
    if status:
        query = query.filter(Foreshadowing.status == status)
    return query.order_by(Foreshadowing.plant_order).all()


@router.post("/foreshadowings", response_model=ForeshadowingResponse)
async def create_foreshadowing(project_id: int, data: ForeshadowingCreate, db: Session = Depends(get_db)):
    fs = Foreshadowing(project_id=project_id, **data.model_dump())
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


@router.put("/foreshadowings/{fs_id}", response_model=ForeshadowingResponse)
async def update_foreshadowing(project_id: int, fs_id: int, data: ForeshadowingUpdate, db: Session = Depends(get_db)):
    fs = db.query(Foreshadowing).filter(Foreshadowing.id == fs_id, Foreshadowing.project_id == project_id).first()
    if not fs:
        raise HTTPException(status_code=404, detail="Foreshadowing not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(fs, key, value)
    db.commit()
    db.refresh(fs)
    return fs


@router.delete("/foreshadowings/{fs_id}")
async def delete_foreshadowing(project_id: int, fs_id: int, db: Session = Depends(get_db)):
    fs = db.query(Foreshadowing).filter(Foreshadowing.id == fs_id, Foreshadowing.project_id == project_id).first()
    if not fs:
        raise HTTPException(status_code=404, detail="Foreshadowing not found")
    db.delete(fs)
    db.commit()
    return {"status": "ok"}


# ─── ConsistencyRecord Routes ───

@router.get("/consistency")
async def list_consistency(project_id: int, entity_type: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ConsistencyRecord).filter(ConsistencyRecord.project_id == project_id)
    if entity_type:
        query = query.filter(ConsistencyRecord.entity_type == entity_type)
    return query.order_by(ConsistencyRecord.created_at.desc()).all()


@router.post("/consistency")
async def create_consistency(project_id: int, data: ConsistencyRecordCreate, db: Session = Depends(get_db)):
    rec = ConsistencyRecord(project_id=project_id, **data.model_dump())
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.put("/consistency/{record_id}")
async def update_consistency(project_id: int, record_id: int, data: ConsistencyRecordUpdate, db: Session = Depends(get_db)):
    rec = db.query(ConsistencyRecord).filter(
        ConsistencyRecord.id == record_id, ConsistencyRecord.project_id == project_id
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rec, key, value)
    db.commit()
    db.refresh(rec)
    return rec


# ─── CharacterArc Routes ───

@router.get("/character-arcs")
async def list_character_arcs(project_id: int, character_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(CharacterArc).filter(CharacterArc.project_id == project_id)
    if character_id:
        query = query.filter(CharacterArc.character_id == character_id)
    return query.all()


@router.post("/character-arcs")
async def create_character_arc(project_id: int, data: CharacterArcCreate, db: Session = Depends(get_db)):
    arc = CharacterArc(project_id=project_id, **data.model_dump())
    db.add(arc)
    db.commit()
    db.refresh(arc)
    return arc


@router.put("/character-arcs/{arc_id}")
async def update_character_arc(project_id: int, arc_id: int, data: CharacterArcUpdate, db: Session = Depends(get_db)):
    arc = db.query(CharacterArc).filter(CharacterArc.id == arc_id, CharacterArc.project_id == project_id).first()
    if not arc:
        raise HTTPException(status_code=404, detail="Arc not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(arc, key, value)
    db.commit()
    db.refresh(arc)
    return arc


# ─── CharacterRelation Routes ───

@router.get("/character-relations")
async def list_character_relations(project_id: int, db: Session = Depends(get_db)):
    return db.query(CharacterRelation).filter(CharacterRelation.project_id == project_id).all()


@router.post("/character-relations")
async def create_character_relation(project_id: int, data: CharacterRelationCreate, db: Session = Depends(get_db)):
    rel = CharacterRelation(project_id=project_id, **data.model_dump())
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


@router.put("/character-relations/{rel_id}")
async def update_character_relation(project_id: int, rel_id: int, data: CharacterRelationUpdate, db: Session = Depends(get_db)):
    rel = db.query(CharacterRelation).filter(
        CharacterRelation.id == rel_id, CharacterRelation.project_id == project_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(rel, key, value)
    db.commit()
    db.refresh(rel)
    return rel


@router.delete("/character-relations/{rel_id}")
async def delete_character_relation(project_id: int, rel_id: int, db: Session = Depends(get_db)):
    rel = db.query(CharacterRelation).filter(
        CharacterRelation.id == rel_id, CharacterRelation.project_id == project_id
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relation not found")
    db.delete(rel)
    db.commit()
    return {"status": "ok"}
