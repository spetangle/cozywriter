"""Theme / Foreshadowing 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Theme(Base):
    """小说核心主旨 / 作者意图"""
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    theme_type = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    related_theme_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="themes")


class Foreshadowing(Base):
    """伏笔管理"""
    __tablename__ = "foreshadowings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    plant_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    resolve_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    plant_order = Column(Integer, default=0)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="foreshadowings")
