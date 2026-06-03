"""Character 相关模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Character(Base):
    """角色"""
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="配角")
    profile = Column(JSON, default=dict)
    description = Column(Text, default="")
    avatar = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def profile_text(self) -> str:
        parts = [f"【角色: {self.name}】"]
        if self.role:
            parts.append(f"身份: {self.role}")
        if self.profile:
            for key, value in self.profile.items():
                if value:
                    parts.append(f"{key}: {value}")
        if self.description:
            parts.append(f"补充设定: {self.description}")
        return "\n".join(parts)

    project = relationship("Project", back_populates="characters")
    arcs = relationship("CharacterArc", back_populates="character", cascade="all, delete-orphan")
    consistency_records = relationship("ConsistencyRecord", back_populates="character")
    relations_from = relationship(
        "CharacterRelation", foreign_keys="CharacterRelation.from_character_id", back_populates="from_character"
    )
    relations_to = relationship(
        "CharacterRelation", foreign_keys="CharacterRelation.to_character_id", back_populates="to_character"
    )


class CharacterArc(Base):
    """角色弧光"""
    __tablename__ = "character_arcs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    arc_type = Column(String(30), nullable=False)
    start_state = Column(Text, default="")
    end_state = Column(Text, default="")
    current_state = Column(Text, default="")
    key_behavior = Column(Text, default="")
    is_stable = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="character_arcs")
    character = relationship("Character", back_populates="arcs")


class CharacterRelation(Base):
    """角色关系矩阵"""
    __tablename__ = "character_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    to_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    strength = Column(Integer, default=5)
    status = Column(String(20), default="stable")
    is_consistent = Column(Boolean, default=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_character = relationship("Character", foreign_keys=[from_character_id], back_populates="relations_from")
    to_character = relationship("Character", foreign_keys=[to_character_id], back_populates="relations_to")
