"""CreativeQuestionnaire 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from storage.models.base import Base


class CreativeQuestionnaire(Base):
    """
    创意问卷记录

    问卷是一组预设问题的答案，最终可用于生成项目初始化配置。
    不绑定具体 Project，保留为独立模板。
    """
    __tablename__ = "creative_questionnaires"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), default="未命名问卷")
    # 问卷答案（JSON）
    answers = Column(JSON, default=dict)
    # 预设问卷类型
    questionnaire_type = Column(String(50), default="novel")
    # 状态
    status = Column(String(20), default="draft")  # draft / completed
    # 基于此问卷创建的项目 ID（创建后填入）
    created_project_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── 预设问卷题目定义（静态，供前端渲染使用） ───

QUESTIONNAIRE_QUESTIONS = [
    {
        "id": "genre",
        "question": "小说类型是什么？",
        "type": "select",
        "options": ["玄幻", "都市", "科幻", "武侠", "仙侠", "历史", "悬疑", "现实主义", "奇幻", "其他"],
        "required": True,
    },
    {
        "id": "theme",
        "question": "小说的核心主题是什么？",
        "type": "text",
        "placeholder": "例如：救赎、成长、复仇、爱情、命运...",
        "required": True,
    },
    {
        "id": "premise",
        "question": "故事的世界观/背景设定是什么？",
        "type": "textarea",
        "placeholder": "描述故事发生的世界、时代、社会规则...",
        "required": True,
    },
    {
        "id": "protagonist",
        "question": "主角是谁？简要描述主角的性格和目标。",
        "type": "textarea",
        "placeholder": "名字、性格特征、核心目标、矛盾冲突...",
        "required": True,
    },
    {
        "id": "antagonist",
        "question": "反派/主要冲突方是谁？",
        "type": "textarea",
        "placeholder": "反派的目标是什么？与主角的核心矛盾是什么？",
        "required": False,
    },
    {
        "id": "supporting",
        "question": "有哪些重要配角？",
        "type": "textarea",
        "placeholder": "列出重要配角及其与主角的关系...",
        "required": False,
    },
    {
        "id": "tone",
        "question": "小说的整体基调是什么？",
        "type": "select",
        "options": ["热血", "治愈", "黑暗", "轻松", "史诗", "悬疑紧张", "浪漫", "幽默", "冷峻"],
        "required": True,
    },
    {
        "id": "target_length",
        "question": "预计写多长？",
        "type": "select",
        "options": ["短篇（3-10万字）", "中篇（10-30万字）", "长篇（30-100万字）", "超长篇（100万字以上）"],
        "required": True,
    },
    {
        "id": "pacing",
        "question": "节奏偏好？",
        "type": "select",
        "options": ["快节奏", "中等节奏", "慢热型", "起伏型"],
        "required": False,
    },
    {
        "id": "style",
        "question": "文笔风格偏好？",
        "type": "select",
        "options": ["优美", "平实", "诗意", "幽默", "冷峻"],
        "required": True,
    },
    {
        "id": "summary",
        "question": "用一段话描述你的故事（可选）",
        "type": "textarea",
        "placeholder": "这是可选的，帮助整理思路...",
        "required": False,
    },
    {
        "id": "notes",
        "question": "还有什么特别想写的设定或创意？",
        "type": "textarea",
        "placeholder": "独特的世界观、有趣的设定、脑洞...",
        "required": False,
    },
]
