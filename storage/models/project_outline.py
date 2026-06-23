"""ProjectOutline / ChapterOutline 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class ProjectOutline(Base):
    """小说大纲 - 项目级整体剧情规划"""
    __tablename__ = "project_outlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    plot_lines = Column(JSON, default=list)
    structure = Column(JSON, default=dict)
    pacing_notes = Column(Text, default="")
    outline_text = Column(Text, default="")
    reversal_schedule = Column(JSON, default=dict)  # 宏观节奏：小爽点(每3章) + 大爽点(每10章)
    climax_map = Column(JSON, default=list)  # 每幕高潮点安排
    volumes = Column(JSON, default=list)  # 分卷结构：每卷一个完整剧情阶段（title/summary/from_chapter/to_chapter/core_event）
    chapter_outlines = Column(JSON, default=list)  # 每章一句话核心事件（stage_4a_chapter_outlines 写入）
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
    volume_num = Column(Integer, default=0)  # 所属卷号（1-based，0=未分卷）
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
    qi_cheng_zhuan_he = Column(JSON, default=dict)  # 起承转合四阶段结构
    pacing_hooks = Column(JSON, default=list)  # 章内钩子（每500字一个小转折）
    reversals = Column(JSON, default=list)  # 本章反转安排
    status = Column(String(20), default="planning")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="outline")
