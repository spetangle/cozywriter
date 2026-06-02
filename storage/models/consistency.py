"""ConsistencyRecord 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from storage.models.base import Base


class ConsistencyRecord(Base):
    """一致性记录：跟踪角色/物品/能力/资源的状态变化"""
    __tablename__ = "consistency_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(Integer, nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    property_name = Column(String(100), nullable=False)
    old_value = Column(Text, default="")
    new_value = Column(Text, default="")
    reason = Column(Text, default="")
    is_consistent = Column(Boolean, default=True)
    inconsistency_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="consistency_records")
    character = relationship("Character", back_populates="consistency_records")
