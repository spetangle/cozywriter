"""剧情点模型（PlotPoint）"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from storage.models.base import Base


class PlotPoint(Base):
    """剧情点

    一个剧情点是一条贯穿小说的故事线索 / 关键节点，
    通过多个阶段（引入/发展/高潮/回收）分布在不同章节。
    与 Foreshadowing（伏笔）的区别：
      - Foreshadowing 专注于"埋设→回收"的二段式；
      - PlotPoint 更通用：可记录 4 个阶段的章节号，覆盖任何剧情线。
    """
    __tablename__ = "plot_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    tags = Column(JSON, default=list)             # 标签，如 ["主线","悬疑","感情线"]
    importance = Column(String(10), default="major")  # major 主线 / minor 支线
    status = Column(String(20), default="planning")   # planning/introduced/developing/climaxed/resolved/abandoned

    # 四个阶段的章节锚点（可空）
    intro_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    develop_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    climax_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    resolve_chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    # 各阶段备注（与对应章节联动）
    intro_note = Column(Text, default="")
    develop_note = Column(Text, default="")
    climax_note = Column(Text, default="")
    resolve_note = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="plot_points")