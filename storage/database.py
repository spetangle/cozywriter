"""数据库初始化"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import settings
from pathlib import Path

# 确保 data 目录存在
Path("./data").mkdir(exist_ok=True)

# SQLite 方言使用 aiosqlite 需同步兼容
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库表"""
    from storage.models import Base
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """获取数据库会话（FastAPI 依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
