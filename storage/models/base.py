"""SQLAlchemy Base"""
import secrets
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


def generate_project_id() -> str:
    """生成 8 位 hex 字符串作为项目 ID。

    16^8 = 42 亿种组合,在数千项目规模下碰撞概率极低。
    使用 secrets 模块保证密码学级别的随机性(防枚举)。
    格式:8 位小写 hex,例如 'a3f5e2c1'。
    """
    return secrets.token_hex(4)