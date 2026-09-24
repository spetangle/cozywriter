"""CreativeQuestionnaire 模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from storage.models.base import Base


class CreativeQuestionnaire(Base):
    """
    创意问卷记录

    问卷是一组预设问题的答案，最终可用于生成项目初始化配置。
    不绑定具体 Project，保留为独立模板。
    
    支持LLM对话机制：
    - 前面的答案作为上下文传递给LLM
    - LLM根据上下文生成后续问题的选项
    - 用户可以选择预设选项或自定义答案
    - 小说名作为最后一个问题，由LLM根据前面的设定生成建议选项
    """
    __tablename__ = "creative_questionnaires"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), default="未命名问卷")
    # 小说名称（必填，作为最后一个问题）
    novel_title = Column(String(200), nullable=True)
    # 问卷答案（JSON）
    answers = Column(JSON, default=dict)
    # LLM生成的答案/建议（JSON）
    llm_suggestions = Column(JSON, default=dict)
    # 预设问卷类型
    questionnaire_type = Column(String(50), default="novel")
    # 状态: draft / in_progress / completed / cancelled / ai_completed
    status = Column(String(20), default="draft")
    # 当前步骤（分步问卷使用）
    current_step = Column(Integer, default=0)
    # AI 补全的答案（用户选择跳过问卷时使用）
    ai_completed_answers = Column(JSON, default=dict)
    # 基于此问卷创建的项目 ID（创建后填入）
    created_project_id = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── 分步问卷题目定义（支持LLM对话） ───

STEP_QUESTIONS = [
    {
        "step": 0,
        "id": "genre",
        "question": "小说的题材是什么？",
        "type": "step_multiselect_tags",
        "source": "api/genres",
        "custom_input": {
            "type": "text",
            "placeholder": "自定义题材标签（回车添加）",
        },
        "required": True,
        "next_step": 1,
        "llm_enabled": False,
    },
    {
        "step": 1,
        "id": "core_hook",
        "question": "小说的核心看点是什么？",
        "type": "step_choice",
        "options": [
            {"value": "独特设定", "label": "独特设定", "description": "新奇的世界观或规则设定"},
            {"value": "人物成长", "label": "人物成长", "description": "主角从弱小到强大的成长历程"},
            {"value": "反转剧情", "label": "反转剧情", "description": "出人意料的情节发展"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "描述小说最吸引人的核心看点...",
        },
        "required": True,
        "next_step": 2,
        "llm_enabled": True,
    },
    {
        "step": 2,
        "id": "theme",
        "question": "小说想要表达的核心主题是什么？",
        "type": "step_choice",
        "options": [
            {"value": "成长", "label": "成长", "description": "主角在历练中不断成长变强"},
            {"value": "救赎", "label": "救赎", "description": "主角或角色的自我救赎之路"},
            {"value": "抗争", "label": "抗争", "description": "对抗命运、不公或强大敌人"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "其他主题（如：爱情、友情、自由...）",
        },
        "required": True,
        "next_step": 3,
        "llm_enabled": True,
    },
    {
        "step": 3,
        "id": "protagonist",
        "question": "主角是什么样的人？",
        "type": "step_multiselect",
        "options": [
            {"value": "平凡少年", "label": "平凡少年", "description": "出身平凡，靠努力逆袭"},
            {"value": "天才强者", "label": "天才强者", "description": "天赋异禀，一路碾压"},
            {"value": "悲剧英雄", "label": "悲剧英雄", "description": "背负沉重命运，悲壮前行"},
            {"value": "反英雄", "label": "反英雄", "description": "不完美但有魅力的主角"},
            {"value": "成长型", "label": "成长型", "description": "在故事中不断成长"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "详细描述主角的性格、目标、背景...",
        },
        "required": True,
        "next_step": 4,
        "llm_enabled": True,
    },
    {
        "step": 4,
        "id": "protagonist_name",
        "question": "主角叫什么名字？（AI 会根据之前的设定生成具有关联性或隐喻的名字供选择）",
        "type": "step_choice",
        "options": [
            {"value": "林墨白", "label": "林墨白", "description": "隐喻：笔墨生花，清白正直，寓意主角以文载道、坚守本心"},
            {"value": "顾临风", "label": "顾临风", "description": "隐喻：玉树临风，潇洒不羁，象征主角坦荡洒脱的气度"},
            {"value": "苏晚晴", "label": "苏晚晴", "description": "隐喻：雨过天晴，寓意主角历经磨难终见曙光"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "输入主角姓名（AI 会根据你的设定推荐名字）",
        },
        "required": True,
        "next_step": 5,
        "llm_enabled": True,
        "llm_prompt": "根据之前的小说设定（题材：{genre}，核心看点：{core_hook}，主题：{theme}，主角类型：{protagonist}），生成3个主角姓名。\n\n硬性要求：\n1. 必须是全名（姓+名），如「林墨白」「顾临风」，不要只给单名或昵称\n2. 严禁叠字（如「圆圆」「婷婷」「墨墨」这类重复字）\n3. 严禁谐音梗（如「钱多多」「白奋斗」这类玩谐音的名字）\n4. 严禁生僻字（使用常用汉字，避免异体字、繁体字、冷僻字）\n5. 严禁负能量（避免含有死亡、黑暗、悲伤、衰败等负面寓意的字，如「死」「冥」「血」「凋」「丧」等）\n6. 3个名字必须各不相同，严禁出现任何重复或相似的名字\n\n名字须有正面寓意或与设定相关联的隐喻，风格典雅大气。格式为JSON数组，每个元素包含value（名字）、label（名字）、description（寓意或含义说明）。",
    },
    {
        "step": 5,
        "id": "antagonist",
        "question": "主要反派或冲突来源是什么？",
        "type": "step_choice",
        "options": [
            {"value": "宿敌", "label": "宿敌", "description": "与主角有深仇大恨的对手"},
            {"value": "命运", "label": "命运", "description": "不可抗拒的命运或宿命"},
            {"value": "体制", "label": "体制", "description": "腐朽的社会制度或规则"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "详细描述反派的动机、背景和与主角的矛盾...",
        },
        "required": False,
        "next_step": 6,
        "llm_enabled": True,
    },
    {
        "step": 6,
        "id": "world_setting",
        "question": "故事发生在什么样的世界？",
        "type": "step_multiselect",
        "options": [
            {"value": "东方玄幻世界", "label": "东方玄幻", "description": "古老宗门、武道修炼、仙侠体系"},
            {"value": "现代都市", "label": "现代都市", "description": "繁华都市、隐藏秘密、都市传说"},
            {"value": "架空世界", "label": "架空世界", "description": "完全虚构的大陆或星球"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "详细描述世界的规则、历史、地理...",
        },
        "required": True,
        "next_step": 7,
        "llm_enabled": True,
    },
    {
        "step": 7,
        "id": "society_structure",
        "question": "这个世界的社会结构是怎样的？",
        "type": "step_multiselect",
        "options": [
            {"value": "等级森严", "label": "等级森严", "description": "明确的阶级划分，底层难以逾越"},
            {"value": "自由平等", "label": "自由平等", "description": "相对公平的社会，靠能力说话"},
            {"value": "混乱无序", "label": "混乱无序", "description": "弱肉强食，没有统一规则"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "描述社会的组织形式、权力结构、价值观...",
        },
        "required": False,
        "next_step": 8,
        "llm_enabled": True,
    },
    {
        "step": 8,
        "id": "tone",
        "question": "小说的整体基调是什么？",
        "type": "step_multiselect",
        "options": [
            {"value": "热血", "label": "热血", "description": "充满激情、奋斗不息"},
            {"value": "深沉", "label": "深沉", "description": "思考人性、引人深思"},
            {"value": "轻松", "label": "轻松", "description": "幽默风趣、轻松愉快"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "其他基调（如：黑暗、治愈、史诗...）",
        },
        "required": True,
        "next_step": 9,
        "llm_enabled": True,
    },
    {
        "step": 9,
        "id": "chapter_word_count",
        "question": "每章目标字数？",
        "type": "step_choice",
        "options": [
            {"value": "2000", "label": "2000字", "description": "精简紧凑，适合快节奏故事"},
            {"value": "3000", "label": "3000字", "description": "适中篇幅，兼顾节奏与细节"},
            {"value": "5000", "label": "5000字", "description": "详尽描写，适合铺垫展开"},
            {"value": "8000", "label": "8000字", "description": "大幅章节，适合深度叙事"},
            {"value": "10000", "label": "10000字", "description": "超长章节，适合大场面"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "自定义字数（1000的整数倍）",
        },
        "required": True,
        "next_step": 10,
        "llm_enabled": False,
    },
    {
        "step": 10,
        "id": "total_chapters",
        "question": "预计写多少章？",
        "type": "step_choice",
        "options": [
            {"value": "30", "label": "30章", "description": "短篇故事，快速完本"},
            {"value": "50", "label": "50章", "description": "中篇故事，有足够展开空间"},
            {"value": "100", "label": "100章", "description": "长篇故事，宏大叙事"},
            {"value": "150", "label": "150章", "description": "超长篇故事，适合连载"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "自定义章节数",
        },
        "required": True,
        "next_step": 11,
        "llm_enabled": False,
    },
    {
        "step": 11,
        "id": "style",
        "question": "文笔风格偏好？",
        "type": "step_multiselect",
        "options": [
            {"value": "平实", "label": "平实", "description": "简洁明了，通俗易懂"},
            {"value": "优美", "label": "优美", "description": "辞藻华丽，富有文采"},
            {"value": "冷峻", "label": "冷峻", "description": "冷静克制，理性客观"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "其他风格（如：幽默、诗意...）",
        },
        "required": True,
        "next_step": 12,
        "llm_enabled": True,
    },
    {
        "step": 12,
        "id": "pacing",
        "question": "故事节奏偏好？",
        "type": "step_multiselect",
        "options": [
            {"value": "快节奏", "label": "快节奏", "description": "情节紧凑，高潮迭起"},
            {"value": "中等节奏", "label": "中等节奏", "description": "张弛有度，循序渐进"},
            {"value": "慢热型", "label": "慢热型", "description": "铺垫充分，渐入佳境"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "其他节奏偏好",
        },
        "required": False,
        "next_step": 13,
        "llm_enabled": True,
    },
    {
        "step": 13,
        "id": "romance_type",
        "question": "小说的恋爱关系/CP设定？",
        "type": "step_multiselect",
        "options": [
            {"value": "无CP", "label": "无CP", "description": "无伴侣、无情感线，专注于剧情"},
            {"value": "单CP", "label": "单CP", "description": "主角有一个固定伴侣"},
            {"value": "多CP", "label": "多CP", "description": "主角有多个伴侣或多条情感线"},
            {"value": "暧昧向", "label": "暧昧向", "description": "情感关系若即若离，点到为止"},
            {"value": "暗恋", "label": "暗恋", "description": "单向的情感，未表白或未回应"},
        ],
        "custom_input": {
            "type": "textarea",
            "placeholder": "详细描述CP设定、CP角色名字或情感发展方向...",
        },
        "required": False,
        "next_step": 14,
        "llm_enabled": True,
    },
    {
        "step": 14,
        "id": "novel_title",
        "question": "小说的名称是什么？",
        "type": "step_choice",
        "options": [
            {"value": "未命名", "label": "未命名", "description": "暂时未定，后续再命名"},
        ],
        "custom_input": {
            "type": "text",
            "placeholder": "输入自定义小说名称",
        },
        "required": True,
        "next_step": 15,
        "llm_enabled": True,
    },
    {
        "step": 15,
        "id": "summary",
        "question": "问卷信息汇总",
        "type": "step_summary",
        "required": False,
        "next_step": -1,
        "llm_enabled": False,
    },
]

TOTAL_STEPS = len(STEP_QUESTIONS)


# ─── 兼容旧版的完整问卷题目（供旧版页面使用） ───

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
        "id": "novel_title",
        "question": "小说的名称是什么？",
        "type": "text",
        "placeholder": "输入小说名称（可选，可后续修改）",
        "required": False,
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
