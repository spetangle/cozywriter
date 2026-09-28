"""系统级设置模型（key-value 存储）"""
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from storage.models.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True)
    value = Column(String(4096), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 内置的 key 常量
    KEY_DEFAULT_LLM_PROVIDER = "default_llm_provider"
    # RAG embedding：local=本地 CPU 模型 / online=在线 embedding API
    KEY_RAG_EMBEDDING_MODE = "rag_embedding_mode"        # "local" | "online"
    KEY_RAG_ONLINE_BASE_URL = "rag_online_base_url"
    KEY_RAG_ONLINE_API_KEY = "rag_online_api_key"
    KEY_RAG_ONLINE_MODEL = "rag_online_model"
    # 联网搜索（可选）：tavily | serper
    KEY_SEARCH_PROVIDER = "search_provider"
    KEY_SEARCH_API_KEY = "search_api_key"

    @classmethod
    def get(cls, db, key: str, default: str = "") -> str:
        """读取系统设置，不存在则返回 default"""
        row = db.query(cls).filter(cls.key == key).first()
        return row.value if row else default

    @classmethod
    def set(cls, db, key: str, value: str):
        """写入系统设置，upsert 语义"""
        row = db.query(cls).filter(cls.key == key).first()
        if row:
            row.value = value
            row.updated_at = datetime.utcnow()
        else:
            db.add(cls(key=key, value=value))
        db.commit()