"""Project 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Project(Base):
    """小说项目"""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    word_count = Column(Integer, default=0)
    writing_style = Column(String(50), default="平实")
    ai味去除程度 = Column(Integer, default=7)
    target_word_count = Column(Integer, default=3000)
    word_count_min = Column(Integer, default=2000)
    word_count_max = Column(Integer, default=5000)
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

