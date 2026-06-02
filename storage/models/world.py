"""WorldEntry 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class WorldEntry(Base):
    """世界观条目"""
    __tablename__ = "world_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def summary_text(self) -> str:
        return f"【{self.category}: {self.title}】\n{self.content[:500]}"

    project = relationship("Project", back_populates="world_entries")
