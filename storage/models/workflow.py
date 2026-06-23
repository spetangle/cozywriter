"""Workflow 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from storage.models.base import Base


class WorkflowRun(Base):
    """工作流运行记录"""
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), default="补全工作流")
    # 工作流定义（静态模板引用 + 自定义参数）
    stages = Column(JSON, default=list)  # Stage 配置列表
    # 状态机
    current_stage_index = Column(Integer, default=0)
    status = Column(String(20), default="pending")  # pending/running/paused/completed/failed
    # 结果存储
    stage_results = Column(JSON, default=dict)  # {stage_name: {"status": ok/fail, "data": {...}}
    # LLM 调用记录
    llm_logs = Column(JSON, default=list)  # [{"stage": "...", "prompt": "...", "response": "..."}]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="workflow_runs")
