"""大纲管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import OutlineNode, Project
from datetime import datetime


router = APIRouter(prefix="/api/projects/{project_id}/outline", tags=["大纲"])


# ─── Schemas ───

class OutlineNodeCreate(BaseModel):
    title: str
    content: str = ""
    parent_id: int | None = None
    order: int = 0


class OutlineNodeUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    parent_id: int | None = None
    order: int | None = None


class OutlineNodeResponse(BaseModel):
    id: int
    project_id: int
    parent_id: int | None
    title: str
    content: str
    order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[OutlineNodeResponse])
async def list_outline(project_id: int, db: Session = Depends(get_db)):
    """获取项目大纲"""
    nodes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id)
        .order_by(OutlineNode.order)
        .all()
    )
    return nodes


@router.post("", response_model=OutlineNodeResponse)
async def create_outline_node(project_id: int, data: OutlineNodeCreate, db: Session = Depends(get_db)):
    """创建大纲节点"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    node = OutlineNode(
        project_id=project_id,
        title=data.title,
        content=data.content,
        parent_id=data.parent_id,
        order=data.order,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@router.put("/{node_id}", response_model=OutlineNodeResponse)
async def update_outline_node(project_id: int, node_id: int, data: OutlineNodeUpdate, db: Session = Depends(get_db)):
    """更新大纲节点"""
    node = (
        db.query(OutlineNode)
        .filter(OutlineNode.id == node_id, OutlineNode.project_id == project_id)
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="Outline node not found")

    if data.title is not None:
        node.title = data.title
    if data.content is not None:
        node.content = data.content
    if data.order is not None:
        node.order = data.order
    if data.parent_id is not None:
        node.parent_id = data.parent_id

    db.commit()
    db.refresh(node)
    return node


@router.delete("/{node_id}")
async def delete_outline_node(project_id: int, node_id: int, db: Session = Depends(get_db)):
    """删除大纲节点（会删除所有子节点）"""
    node = (
        db.query(OutlineNode)
        .filter(OutlineNode.id == node_id, OutlineNode.project_id == project_id)
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="Outline node not found")
    db.delete(node)
    db.commit()
    return {"status": "ok"}
