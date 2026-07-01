"""数据库初始化"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from config import settings
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 确保 data 目录存在
Path("./data").mkdir(exist_ok=True)

# 同步 SQLite（项目全用同步 Session，无需 aiosqlite）
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库表 + 自动迁移老 schema"""
    from storage.models import Base
    Base.metadata.create_all(bind=engine)
    # 老项目迁移：int ID → 8 位 hex ID
    try:
        from storage.migrations.migrate_project_ids import migrate_project_ids
        result = migrate_project_ids()
        if result.get("migrated"):
            logger.info(f"[DB migrate] 项目 ID 已迁移: {result}")
    except Exception as e:
        logger.warning(f"[DB migrate] 项目 ID 迁移失败（可忽略首次启动或已是新 schema）: {e}")
    # 修复迁移后丢失 PRIMARY KEY 的 id 列（v1.0 项目ID迁移副作用）
    try:
        from storage.migrations.fix_id_primary_keys import fix_id_primary_keys
        fix_result = fix_id_primary_keys(engine)
        if fix_result.get("tables_fixed"):
            logger.info(f"[DB fix_pk] 修复 PRIMARY KEY: {fix_result['tables_fixed']}")
    except Exception as e:
        logger.warning(f"[DB fix_pk] 修复失败: {e}")
    # 添加问卷新字段（分步问卷功能）
    try:
        from storage.migrations.add_questionnaire_columns import add_questionnaire_columns
        q_result = add_questionnaire_columns(engine)
        if q_result.get("success"):
            logger.info(f"[DB migrate] 问卷新字段添加成功")
    except Exception as e:
        logger.warning(f"[DB migrate] 添加问卷字段失败: {e}")


def get_db() -> Session:
    """获取数据库会话（FastAPI 依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
