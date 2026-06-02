"""ReviewSession 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float, Boolean
from sqlalchemy.orm import relationship
from storage.models.base import Base


class ReviewSession(Base):
    """评审会话"""
    __tablename__ = "review_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True)
    session_type = Column(String(30), default="chapter")
    content_reviewed = Column(Text, default="")
    score_consistency = Column(Float, default=0.0)
    score_pacing = Column(Float, default=0.0)
    score_style = Column(Float, default=0.0)
    score_ai_removal = Column(Float, default=0.0)
    score_word_count = Column(Float, default=0.0)
    score_foreshadowing = Column(Float, default=0.0)
    score_character_arc = Column(Float, default=0.0)
    score_thematic = Column(Float, default=0.0)
    overall_score = Column(Float, default=0.0)
    critique = Column(Text, default="")
    suggestions = Column(JSON, default=list)
    revised = Column(Boolean, default=False)
    original_session_id = Column(Integer, ForeignKey("review_sessions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="review_sessions")
    chapter = relationship("Chapter", back_populates="review_sessions")
