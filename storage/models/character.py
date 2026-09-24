"""Character 相关模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from storage.models.base import Base


# appearance JSON 字段 → 中文标签（顺序即输出顺序）
APPEARANCE_FIELDS = [
    ("age_range", "年龄区间"),
    ("height", "身高"),
    ("build", "体型"),
    ("face", "面部特征"),
    ("hair", "发型发色"),
    ("eyes", "眼睛特征"),
    ("skin", "肤色"),
    ("clothing", "常着服饰"),
    ("accessories", "标志性配饰"),
    ("other", "其他"),
]


class Character(Base):
    """角色"""
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="配角")
    profile = Column(JSON, default=dict)
    description = Column(Text, default="")
    avatar = Column(String(500), default="")
    # 剧本专用：角色详细外貌（JSON）
    appearance = Column(JSON, default=dict)
    # 剧本专用：外貌变化记录（list）
    appearance_changes = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def appearance_text(self) -> str:
        """把 appearance JSON 渲染成可读文本，供 prompt 注入。

        appearance 是 dict（见 APPEARANCE_FIELDS），直接 f-string 会把 Python
        字典 repr 塞进 prompt，故在此统一格式化。空值返回 ""。
        """
        app = self.appearance
        if not app:
            return ""
        if isinstance(app, str):
            return app.strip()
        if not isinstance(app, dict):
            return str(app)

        known = dict(APPEARANCE_FIELDS)
        parts = []
        for key, label in APPEARANCE_FIELDS:
            value = app.get(key)
            if value:
                parts.append(f"{label}: {value}")
        # 保留 LLM 额外产出的字段，避免信息丢失
        for key, value in app.items():
            if value and key not in known:
                parts.append(f"{key}: {value}")
        return "；".join(parts)

    @property
    def profile_text(self) -> str:
        parts = [f"【角色: {self.name}】"]
        if self.role:
            parts.append(f"身份: {self.role}")
        if self.profile:
            for key, value in self.profile.items():
                if value:
                    parts.append(f"{key}: {value}")
        if self.description:
            parts.append(f"补充设定: {self.description}")
        appearance_text = self.appearance_text
        if appearance_text:
            parts.append(f"外貌: {appearance_text}")
        return "\n".join(parts)

    project = relationship("Project", back_populates="characters")
    arcs = relationship("CharacterArc", back_populates="character", cascade="all, delete-orphan")
    consistency_records = relationship("ConsistencyRecord", back_populates="character")
    relations_from = relationship(
        "CharacterRelation", foreign_keys="CharacterRelation.from_character_id",
        back_populates="from_character", passive_deletes=True
    )
    relations_to = relationship(
        "CharacterRelation", foreign_keys="CharacterRelation.to_character_id",
        back_populates="to_character", passive_deletes=True
    )


class CharacterArc(Base):
    """角色弧光"""
    __tablename__ = "character_arcs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    arc_type = Column(String(30), nullable=False)
    start_state = Column(Text, default="")
    end_state = Column(Text, default="")
    current_state = Column(Text, default="")
    key_behavior = Column(Text, default="")
    is_stable = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="character_arcs")
    character = relationship("Character", back_populates="arcs")


class CharacterRelation(Base):
    """角色关系矩阵"""
    __tablename__ = "character_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(32), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    to_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(50), nullable=False)
    description = Column(Text, default="")
    strength = Column(Integer, default=5)
    status = Column(String(20), default="stable")
    is_consistent = Column(Boolean, default=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_character = relationship("Character", foreign_keys=[from_character_id], back_populates="relations_from")
    to_character = relationship("Character", foreign_keys=[to_character_id], back_populates="relations_to")
