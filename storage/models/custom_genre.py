"""CustomGenre - 用户自定义的小说题材（可多选）"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from storage.models.base import Base


class CustomGenre(Base):
    """用户自定义题材（系统内置题材 + 用户自添加的并存）
    - 系统内置：12 种（玄幻/都市/科幻/武侠/仙侠/历史/悬疑/现实主义/奇幻/其他）
    - 用户自添加：通过前端 input 添加，存这里备用
    - 所有用户共享同一个 custom_genres 表（无 project_id）
    """
    __tablename__ = "custom_genres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    is_system = Column(Integer, default=0)  # 1=系统预设（不可删），0=用户自添加
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "is_system": bool(self.is_system),
        }
