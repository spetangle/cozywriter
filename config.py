"""CozyWriter 全局配置"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 确保 data 目录存在
DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider 配置
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_llm_provider: str = "anthropic"

    # Embedding 配置
    embedding_model: str = "moka-ai/m3e-base"
    hf_endpoint: str = "https://hf-mirror.com"

    # 存储路径
    data_dir: str = "./data"
    chroma_persist_dir: str = "./data/chroma"
    database_url: str = "sqlite+aiosqlite:///./data/cozywriter.db"


# 设置 HuggingFace 镜像（国内加速）
os.environ.setdefault("HF_ENDPOINT", Settings().hf_endpoint)

settings = Settings()
