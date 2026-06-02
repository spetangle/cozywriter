"""项目管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from storage.database import get_db
from storage.models import Project
from datetime import datetime


router = APIRouter(prefix="/api/projects", tags=["项目"])


# ─── Pydantic Schemas ───

class ProjectCreate(BaseModel):
    title: str
    description: str = ""


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    writing_style: str | None = None
    ai味去除程度: int | None = None
    target_word_count: int | None = None
    word_count_min: int | None = None
    word_count_max: int | None = None
    total_chapters: int | None = None


class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str
    word_count: int
    writing_style: str
    ai味去除程度: int
    target_word_count: int
    word_count_min: int
    word_count_max: int
    total_chapters: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Routes ───

@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: Session = Depends(get_db)):
    """获取项目列表"""
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return projects


@router.post("", response_model=ProjectResponse)
async def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    """创建项目"""
    project = Project(title=data.title, description=data.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: Session = Depends(get_db)):
    """获取项目详情"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    """更新项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if data.title is not None:
        project.title = data.title
    if data.description is not None:
        project.description = data.description
    if data.writing_style is not None:
        project.writing_style = data.writing_style
    if data.ai味去除程度 is not None:
        project.ai味去除程度 = data.ai味去除程度
    if data.target_word_count is not None:
        project.target_word_count = data.target_word_count
    if data.word_count_min is not None:
        project.word_count_min = data.word_count_min
    if data.word_count_max is not None:
        project.word_count_max = data.word_count_max
    if data.total_chapters is not None:
        project.total_chapters = data.total_chapters
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    """删除项目"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "ok"}
