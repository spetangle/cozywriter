"""添加问卷新字段迁移脚本"""
from sqlalchemy import create_engine, text
from config import settings
import logging

logger = logging.getLogger(__name__)

def add_questionnaire_columns(engine):
    """为 creative_questionnaires 表添加新字段"""
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE creative_questionnaires ADD COLUMN current_step INTEGER DEFAULT 0"))
            except:
                pass
            try:
                conn.execute(text("ALTER TABLE creative_questionnaires ADD COLUMN ai_completed_answers TEXT DEFAULT '{}'"))
            except:
                pass
            conn.commit()
            logger.info("[DB migrate] 问卷新字段添加成功")
            return {"success": True}
    except Exception as e:
        logger.warning(f"[DB migrate] 添加字段失败: {e}")
        return {"success": False, "error": str(e)}