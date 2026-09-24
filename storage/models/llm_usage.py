"""LLM Token 用量记录模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from storage.models.base import Base


class LLMUsageRecord(Base):
    """每次 LLM 调用的 token 用量记录"""
    __tablename__ = "llm_usage_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), nullable=True, index=True)  # 可空：非项目内调用
    task_id = Column(String(64), nullable=True, index=True)    # 主任务ID（pipeline task id）
    llm_call_id = Column(String(64), nullable=True, index=True)  # 子ID（每次LLM调用唯一ID = {task_id}#{seq}）
    provider = Column(String(32), nullable=False)               # anthropic / openai / deepseek / ...
    model = Column(String(128), nullable=False)                  # 模型名
    task_type = Column(String(64), nullable=False, default="generate")  # 任务类型

    # token 用量
    input_tokens = Column(Integer, default=0)                    # 输入 token
    output_tokens = Column(Integer, default=0)                   # 输出 token
    total_tokens = Column(Integer, default=0)                    # 总 token
    cache_read_tokens = Column(Integer, default=0)               # 缓存命中读取的 token
    cache_creation_tokens = Column(Integer, default=0)           # 缓存写入的 token

    # 调用元信息
    duration_ms = Column(Float, default=0.0)                     # 耗时（毫秒）
    success = Column(Integer, default=1)                         # 1=成功 0=失败
    error = Column(String(512), default="")                      # 失败原因

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 索引
    __table_args__ = (
        Index("ix_llm_usage_project_created", "project_id", "created_at"),
        Index("ix_llm_usage_task_id", "task_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "llm_call_id": self.llm_call_id,
            "provider": self.provider,
            "model": self.model,
            "task_type": self.task_type,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "duration_ms": self.duration_ms,
            "success": bool(self.success),
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
