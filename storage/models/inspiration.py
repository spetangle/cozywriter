"""Inspiration 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Inspiration(Base):
    """灵感记录"""
    __tablename__ = "inspirations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)  # 灵感内容
    tags = Column(JSON, default=list)  # 标签列表
    source = Column(String(100), default="")  # 来源：脑洞/阅读/梦境/生活等
    related_characters = Column(JSON, default=list)  # 关联角色 ID 列表
    related_chapters = Column(JSON, default=list)  # 关联章节 ID 列表
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="inspirations")
