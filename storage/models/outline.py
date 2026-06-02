"""OutlineNode 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from storage.models.base import Base


class OutlineNode(Base):
    """大纲节点（树形结构）"""
    __tablename__ = "outline_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("outline_nodes.id", ondelete="CASCADE"), nullable=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, default="")
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="outline_nodes")
    parent = relationship("OutlineNode", remote_side=[id], back_populates="children")
    children = relationship("OutlineNode", back_populates="parent", cascade="all, delete-orphan")
