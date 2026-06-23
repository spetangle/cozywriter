"""Project 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from storage.models.base import Base, generate_project_id


class Project(Base):
    """小说项目"""
    __tablename__ = "projects"

    # ID: 8 位 hex 字符串（不再是自增 int）
    # 老项目迁移时由 migrate_project_ids 脚本批量转成 hex
    # 新项目通过 default=generate_project_id 自动生成
    id = Column(String(32), primary_key=True, default=generate_project_id)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    genre = Column(String(200), default="")  # 题材（逗号分隔）
    word_count = Column(Integer, default=0)
    writing_style = Column(String(50), default="平实")
    ai味去除程度 = Column(Integer, default=7)
    target_word_count = Column(Integer, default=3000)
    word_count_min = Column(Integer, default=2700)
    word_count_max = Column(Integer, default=3300)
    total_chapters = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships (cross-file, resolved by __init__.py)
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    world_entries = relationship("WorldEntry", back_populates="project", cascade="all, delete-orphan")
    outline_nodes = relationship("OutlineNode", back_populates="project", cascade="all, delete-orphan")
    themes = relationship("Theme", back_populates="project", cascade="all, delete-orphan")
    foreshadowings = relationship("Foreshadowing", back_populates="project", cascade="all, delete-orphan")
    consistency_records = relationship("ConsistencyRecord", back_populates="project", cascade="all, delete-orphan")
    character_arcs = relationship("CharacterArc", back_populates="project", cascade="all, delete-orphan")
    review_sessions = relationship("ReviewSession", back_populates="project", cascade="all, delete-orphan")
    project_outline = relationship("ProjectOutline", back_populates="project", uselist=False, cascade="all, delete-orphan")
    inspirations = relationship("Inspiration", back_populates="project", cascade="all, delete-orphan")
    workflow_runs = relationship("WorkflowRun", back_populates="project", cascade="all, delete-orphan")
    plot_points = relationship("PlotPoint", back_populates="project", cascade="all, delete-orphan")

