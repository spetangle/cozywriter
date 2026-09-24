"""道具 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project
from storage.models.screenplay import Property
from logger import logger


router = APIRouter(prefix="/api/projects/{project_id}/properties", tags=["道具"])


# ─── Routes ───

@router.get("")
async def list_properties(project_id: str, db: Session = Depends(get_db)):
    """获取道具列表"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    properties = (
        db.query(Property)
        .filter(Property.project_id == project_id)
        .order_by(Property.id)
        .all()
    )
    return [
        {
            "id": p.id,
            "project_id": p.project_id,
            "name": p.name,
            "type": p.type,
            "description": p.description,
            "origin": p.origin,
            "owner": p.owner,
            "status": p.status,
            "history": p.history,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in properties
    ]


@router.post("")
async def create_property(project_id: str, data: dict, db: Session = Depends(get_db)):
    """创建道具"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    prop = Property(
        project_id=project_id,
        name=data.get("name", "未知道具"),
        type=data.get("type", "道具"),
        description=data.get("description", ""),
        origin=data.get("origin", ""),
        owner=data.get("owner", ""),
        status=data.get("status", "完好"),
        history=data.get("history", []),
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return {
        "id": prop.id,
        "project_id": prop.project_id,
        "name": prop.name,
        "type": prop.type,
        "description": prop.description,
        "origin": prop.origin,
        "owner": prop.owner,
        "status": prop.status,
        "history": prop.history,
    }


@router.put("/{property_id}")
async def update_property(project_id: str, property_id: int, data: dict, db: Session = Depends(get_db)):
    """更新道具"""
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.project_id == project_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    updatable_fields = ["name", "type", "description", "origin", "owner", "status", "history"]
    for field in updatable_fields:
        if field in data and data[field] is not None:
            setattr(prop, field, data[field])

    db.commit()
    db.refresh(prop)
    return {
        "id": prop.id,
        "project_id": prop.project_id,
        "name": prop.name,
        "type": prop.type,
        "description": prop.description,
        "origin": prop.origin,
        "owner": prop.owner,
        "status": prop.status,
        "history": prop.history,
    }


@router.post("/{property_id}/history")
async def append_property_history(project_id: str, property_id: int, data: dict, db: Session = Depends(get_db)):
    """追加一条道具流转记录

    与 PUT 的整体替换不同，此处只做 append，避免客户端读-改-写整个 history。
    history 是普通 JSON 列（未包 Mutable），必须赋新对象才会被 SQLAlchemy 检测到。
    """
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.project_id == project_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    entry = {
        "action": data.get("action", ""),
        "description": data.get("description", ""),
    }
    if data.get("owner"):
        entry["owner"] = data["owner"]
        prop.owner = data["owner"]
    if data.get("status"):
        prop.status = data["status"]

    prop.history = list(prop.history or []) + [entry]

    db.commit()
    db.refresh(prop)
    return {
        "id": prop.id,
        "project_id": prop.project_id,
        "name": prop.name,
        "type": prop.type,
        "description": prop.description,
        "origin": prop.origin,
        "owner": prop.owner,
        "status": prop.status,
        "history": prop.history,
    }


@router.delete("/{property_id}")
async def delete_property(project_id: str, property_id: int, db: Session = Depends(get_db)):
    """删除道具"""
    prop = db.query(Property).filter(
        Property.id == property_id,
        Property.project_id == project_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    db.delete(prop)
    db.commit()
    return {"detail": "Deleted"}
