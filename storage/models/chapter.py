"""Chapter 相关模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Chapter(Base):
    """章节"""
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    order = Column(Integer, default=0)
    content = Column(Text, default="")
    word_count = Column(Integer, default=0)
    synopsis = Column(Text, default="")
    event_signature = Column(Text, default="")  # LLM 抽取的 1-2 句事件签名（用于 RAG 去重检索）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def summary(self) -> str:
        return f"【第{self.order + 1}章 {self.title}】\n{self.synopsis or self.content[:500]}"

    @property
    def event_signature_text(self) -> str:
        """用于 RAG chapter_events 集合的文档文本。优先级:event_signature > synopsis > content[:300]。"""
        sig = (self.event_signature or "").strip()
        if sig:
            return f"【第{self.order + 1}章 {self.title}】\n{sig}"
        # 降级:无 event_signature 时,用 synopsis 或正文前 300 字
        body = (self.synopsis or (self.content or "")[:300]).strip()
        return f"【第{self.order + 1}章 {self.title}】\n{body}"

    project = relationship("Project", back_populates="chapters")
    versions = relationship("ChapterVersion", back_populates="chapter", cascade="all, delete-orphan")
    review_sessions = relationship("ReviewSession", back_populates="chapter", cascade="all, delete-orphan")
    outline = relationship("ChapterOutline", back_populates="chapter", uselist=False, cascade="all, delete-orphan")


class ChapterVersion(Base):
    """章节版本历史"""
    __tablename__ = "chapter_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    version_num = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="versions")

