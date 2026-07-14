"""全文评审模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from storage.models.base import Base


class FullReviewSession(Base):
    """全文评审会话"""
    __tablename__ = "full_review_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # 五维度评分（0-10分）
    score_story = Column(Float, default=0.0)  # 故事与情节
    score_character = Column(Float, default=0.0)  # 人物塑造
    score_prose = Column(Float, default=0.0)  # 文笔与语言
    score_theme = Column(Float, default=0.0)  # 主题与立意
    score_market = Column(Float, default=0.0)  # 创新与市场潜力
    
    # 各维度评审依据（JSON格式，包含评分理由）
    rationale_story = Column(Text, default="")
    rationale_character = Column(Text, default="")
    rationale_prose = Column(Text, default="")
    rationale_theme = Column(Text, default="")
    rationale_market = Column(Text, default="")
    
    # 综合评价
    overall_score = Column(Float, default=0.0)  # 综合评分（加权平均）
    overall_critique = Column(Text, default="")  # 总体评价
    improvement_suggestions = Column(JSON, default=list)  # 改进建议
    
    # 评审元数据
    total_chapters = Column(Integer, default=0)  # 评审章节数
    total_words = Column(Integer, default=0)  # 评审总字数
    batch_count = Column(Integer, default=0)  # 分批评审批次数
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", backref="full_reviews")