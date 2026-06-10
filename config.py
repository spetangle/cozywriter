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
    # MiniMax 配置
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M2.7"
    minimax_base_url: str = "https://api.minimaxi.com/anthropic"
    # Xiaomi MiMo 配置
    mimo_api_key: str = ""
    mimo_model: str = "mimo-v2.5-pro"
    mimo_base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic"
    # 默认 LLM Provider（值为空字符串时，由 LLMFactory 从数据库 SystemSetting 读取回退）
    default_llm_provider: str = ""

    # Embedding 配置
    embedding_model: str = "moka-ai/m3e-base"
    hf_endpoint: str = "https://hf-mirror.com"

    # 存储路径
    data_dir: str = "./data"
    chroma_persist_dir: str = "./data/chroma"
    # 同步 SQLite（项目全用同步 Session，无需 aiosqlite）
    database_url: str = "sqlite:///./data/cozywriter.db"


# 设置 HuggingFace 镜像（国内加速）
os.environ.setdefault("HF_ENDPOINT", Settings().hf_endpoint)

settings = Settings()
