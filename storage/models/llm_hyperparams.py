"""LLM 超参数配置模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, JSON, DateTime
from storage.models.base import Base


class LLMHyperparamPreset(Base):
    """LLM 超参数预设配置"""
    __tablename__ = "llm_hyperparam_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(32), nullable=False)  
    task_type = Column(String(64), nullable=False)  
    name = Column(String(128), nullable=False)  
    description = Column(String(512), default="")
    temperature = Column(Float, default=0.7)
    top_p = Column(Float, default=1.0)
    max_tokens = Column(Integer, default=4096)
    frequency_penalty = Column(Float, default=0.0)
    presence_penalty = Column(Float, default=0.0)
    top_k = Column(Integer, default=0)
    repetition_penalty = Column(Float, default=1.0)
    extra_params = Column(JSON, default=dict)
    is_active = Column(Integer, default=1)  
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    TASK_TYPES = [
        "generate_character",    
        "generate_outline",      
        "generate_chapter_outline", 
        "generate_chapter_text",    
        "review",                 
        "consistency_check",       
        "revision",                
        "golden_3_check",          
        "post_chapter",            
        "foreshadow_updater",      
        "event_signature_extractor",
        "expander",               
        "compressor",              
        "revision_decider",        
        "outline_reviewer",        
        "default",                 
    ]

    PROVIDERS = ["openai", "anthropic", "ollama", "minimax", "mimo"]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "provider": self.provider,
            "task_type": self.task_type,
            "name": self.name,
            "description": self.description,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
            "extra_params": self.extra_params,
            "is_active": bool(self.is_active),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_params(self) -> dict:
        """获取用于 LLM 调用的参数字典"""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            **self.extra_params,
        }