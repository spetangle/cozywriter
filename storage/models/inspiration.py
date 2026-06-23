"""Inspiration 模型 - 灵感池（支持全局 + 项目关联两种模式）"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Inspiration(Base):
    """灵感记录（精简草稿本）
    - project_id IS NULL  → 全局灵感池
    - project_id IS NOT NULL → 绑定到该项目的灵感
    """
    __tablename__ = "inspirations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 关键：project_id 改为可空
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(200), default="")  # 灵感标题（一句话）
    content = Column(Text, nullable=False)  # 灵感内容
    tags = Column(JSON, default=list)  # 标签列表
    source = Column(String(100), default="")  # 来源：脑洞/阅读/梦境/生活等
    # 关联：可关联到任何项目的角色/章节（即使灵感本身不在该项目）
    related_characters = Column(JSON, default=list)  # [{"project_id":1, "character_id":2}]
    related_chapters = Column(JSON, default=list)    # [{"project_id":1, "chapter_id":5}]
    # 用途追踪
    is_consumed = Column(Integer, default=0)  # 0/1：是否已被"融合"到项目中
    consumed_at = Column(DateTime, nullable=True)  # 融合时间
    consumed_into = Column(String(500), default="")  # 融合去向：project_id:chapter_id
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="inspirations")
