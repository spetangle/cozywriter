"""剧本相关模型 - Screenplay（场景剧本）、Storyboard（分镜稿）、Property（道具）"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Screenplay(Base):
    """剧本场景"""
    __tablename__ = "screenplays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    scene_number = Column(Integer, default=0)
    act = Column(String(50), default="第一幕")
    scene_type = Column(String(50), default="对话场景")
    location = Column(String(255), default="")
    time_of_day = Column(String(50), default="白天")
    characters_present = Column(JSON, default=list)
    content = Column(Text, default="")
    word_count = Column(Integer, default=0)
    synopsis = Column(Text, default="")
    fingerprint = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def summary(self) -> str:
        return f"【场景{self.scene_number} {self.title}】\n{self.synopsis or self.content[:300]}"

    project = relationship("Project", back_populates="screenplays")
    storyboards = relationship("Storyboard", back_populates="screenplay", cascade="all, delete-orphan")


class Storyboard(Base):
    """分镜稿"""
    __tablename__ = "storyboards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    screenplay_id = Column(Integer, ForeignKey("screenplays.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    shot_number = Column(Integer, default=1)
    shot_type = Column(String(50), default="中景")
    camera_angle = Column(String(50), default="平视")
    camera_movement = Column(String(50), default="固定")
    duration_estimate = Column(String(50), default="3-5秒")
    location = Column(String(255), default="")
    characters = Column(JSON, default=list)
    visual_description = Column(Text, default="")
    dialogue = Column(Text, default="")
    sound_effects = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    screenplay = relationship("Screenplay", back_populates="storyboards")
    project = relationship("Project", back_populates="storyboards")


class Property(Base):
    """道具"""
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), default="道具")
    description = Column(Text, default="")
    origin = Column(String(100), default="")
    owner = Column(String(100), default="")
    status = Column(String(50), default="完好")
    history = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="properties")
