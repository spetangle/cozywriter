"""ProjectOutline / ChapterOutline 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class ProjectOutline(Base):
    """小说大纲 - 项目级整体剧情规划"""
    __tablename__ = "project_outlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    plot_lines = Column(JSON, default=list)
    structure = Column(JSON, default=dict)
    pacing_notes = Column(Text, default="")
    outline_text = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="project_outline")


class ChapterOutline(Base):
    """章节细纲"""
    __tablename__ = "chapter_outlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, unique=True)
    chapter_position = Column(String(30), default="")
    act_name = Column(String(50), default="")
    key_content = Column(Text, default="")
    plot_advance = Column(Text, default="")
    foreshadow_ids = Column(JSON, default=list)
    foreshadow_notes = Column(Text, default="")
    conflicts = Column(JSON, default=list)
    highlights = Column(JSON, default=list)
    target_word_count = Column(Integer, default=0)
    min_word_count = Column(Integer, default=0)
    max_word_count = Column(Integer, default=0)
    pacing = Column(String(20), default="平稳")
    character_ids = Column(JSON, default=list)
    status = Column(String(20), default="planning")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="outline")
