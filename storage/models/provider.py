"""LLM 服务商配置模型"""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from storage.models.base import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(String(32), primary_key=True)          # slug，如 minimax / mimo / anthropic
    name = Column(String(64), nullable=False)           # 显示名称
    api_key = Column(Text, nullable=True)               # API Key（可空，如 Ollama）
    base_url = Column(String(512), nullable=True)       # 自定义 Base URL
    model = Column(String(128), nullable=True)          # 默认模型名
    is_default = Column(Boolean, default=False)         # 是否为当前默认服务商
    # JSON 模式开关：NULL=按 provider 默认，True=强制开启，False=强制关闭。
    # 部分模型（如某些 DeepSeek 部署）对 response_format 兼容性差，可显式关闭。
    use_json_output = Column(Boolean, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url or "",
            "model": self.model or "",
            "is_default": self.is_default,
            "use_json_output": self.use_json_output,
            # 返回是否已配置 key，不返回明文
            "has_api_key": bool(self.api_key),
        }
